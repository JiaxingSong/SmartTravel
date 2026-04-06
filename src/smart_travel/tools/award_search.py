"""Award/points price search tools for SmartTravel.

Implements the two-step award search flow:
1. Discover which airlines operate a route (via web_search).
2. For each airline with a configured account, log in and scrape award availability.

Each airline scraper is independent; failures are isolated so one blocked site
doesn't prevent results from other airlines.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from claude_agent_sdk import tool

from smart_travel.accounts.sessions import get_session_manager
from smart_travel.accounts.store import LoyaltyAccount, get_account_store, _PROGRAM_NAMES

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AwardResult:
    airline: str        # "united" | "alaska" | "delta" | "aa"
    program: str        # "MileagePlus" | "Mileage Plan" | "SkyMiles" | "AAdvantage"
    origin: str         # "SEA"
    destination: str    # "IAH"
    date: str           # "2026-06-15"
    cabin: str          # "economy" | "business" | "first"
    points: int         # 12500
    taxes_usd: float    # 5.60
    availability: str   # "available" | "waitlist" | "none" | "error"
    source_url: str     # URL used to retrieve results
    notes: str = ""     # "saver award" | "bot challenge detected" | ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_points(text: str) -> int:
    """Parse "12,500 miles" or "12500" → 12500. Returns 0 on failure."""
    if not text:
        return 0
    cleaned = re.sub(r"[^\d]", "", text.replace(",", ""))
    try:
        return int(cleaned)
    except ValueError:
        return 0


def _parse_taxes(text: str) -> float:
    """Parse "$5.60" or "5.60" → 5.60. Returns 0.0 on failure."""
    if not text:
        return 0.0
    m = re.search(r"[\d,]+\.?\d*", text.replace(",", ""))
    if not m:
        return 0.0
    try:
        return float(m.group())
    except ValueError:
        return 0.0


def _normalize_airline(name: str) -> str:
    """Map display airline name to canonical key."""
    _MAP = {
        "united": "united",
        "united airlines": "united",
        "alaska": "alaska",
        "alaska airlines": "alaska",
        "delta": "delta",
        "delta air lines": "delta",
        "delta airlines": "delta",
        "american": "aa",
        "american airlines": "aa",
        "aa": "aa",
    }
    return _MAP.get(name.lower().strip(), name.lower().strip())


def _normalize_date(date_str: str) -> str:
    """Accept MM/DD/YYYY or YYYY-MM-DD; return YYYY-MM-DD."""
    date_str = date_str.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str  # return as-is if unparseable


def _date_to_mmddyyyy(date_str: str) -> str:
    """Convert YYYY-MM-DD → MMDDYYYY (Alaska URL format)."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%m%d%Y")
    except ValueError:
        return date_str


def _is_bot_challenge(url: str, page_text: str) -> bool:
    """Return True if the current page appears to be a bot challenge."""
    url_lower = url.lower()
    if any(x in url_lower for x in ["/blocked", "/challenge", "/captcha", "/403"]):
        return True
    text_lower = page_text.lower()
    return any(x in text_lower for x in [
        "access denied",
        "enable javascript and cookies",
        "checking your browser",
        "ddos-guard",
        "please wait while we check",
        "verify you are human",
    ])


# ---------------------------------------------------------------------------
# Route discovery
# ---------------------------------------------------------------------------

async def _find_airlines_for_route(origin: str, dest: str, date: str) -> list[str]:
    """Return canonical airline keys for carriers operating origin→dest.

    Uses web_search internally to find current operators so the list is
    always up-to-date rather than hard-coded.
    """
    from smart_travel.tools.browser import web_search_tool

    query = (
        f"airlines operating flights from {origin} to {dest} on {date} "
        "nonstop one-stop United Alaska Delta American"
    )
    try:
        result = await web_search_tool.handler({"query": query, "max_results": 10})
        text = result.get("content", [{}])[0].get("text", "")
    except Exception:
        logger.warning("_find_airlines_for_route search failed", exc_info=True)
        text = ""

    found: list[str] = []
    airline_patterns = [
        ("united", r"\bunited\b"),
        ("alaska", r"\balaska\b"),
        ("delta", r"\bdelta\b"),
        ("aa", r"\bamerican\b|\bAA\b|\baadvantage\b"),
        ("southwest", r"\bsouthwest\b"),
        ("frontier", r"\bfrontier\b"),
        ("spirit", r"\bspirit\b"),
    ]
    for key, pattern in airline_patterns:
        if re.search(pattern, text, re.I):
            found.append(key)

    # Always include the "big 4" as fallback if search returned nothing useful
    if not found:
        found = ["united", "alaska", "delta", "aa"]

    return found


# ---------------------------------------------------------------------------
# Shared pool-aware search helper
# ---------------------------------------------------------------------------

async def _search_airline_awards(
    airline: str,
    program: str,
    login_fn: Any,
    verify_fn: Any,
    scrape_fn: Any,
    origin: str,
    dest: str,
    date: str,
    cabin: str,
    max_retries: int = 2,
) -> list[AwardResult]:
    """Pool-aware award search: pick account via LRU rotation, scrape, retry on failure.

    1. get_next_account() returns LRU active account.
    2. Authenticate and call scrape_fn(page, origin, dest, date, cabin).
    3. On success: mark_used(). On failure: mark_cooldown(), retry with next account.
    """
    store = get_account_store()
    session_mgr = get_session_manager()
    results: list[AwardResult] = []

    for attempt in range(max_retries):
        account = store.get_next_account(airline)
        if account is None:
            break

        trio = await session_mgr.get_authenticated_page(account, login_fn, verify_fn)
        if trio is None:
            store.mark_cooldown(account.account_id)
            continue

        browser, context, page = trio
        try:
            scraped = await scrape_fn(page, origin, dest, date, cabin)

            # Check if all results are errors (bot challenge etc)
            has_error_only = scraped and all(r.availability == "error" for r in scraped)
            if has_error_only:
                await session_mgr.invalidate_session(account.account_id)
                store.mark_cooldown(account.account_id)
                results.extend(scraped)
                continue

            if scraped:
                store.mark_used(account.account_id)
                results.extend(scraped)
                break  # Success — no need to retry
            else:
                # Empty results, try next account
                store.mark_used(account.account_id)
                break
        except Exception:
            logger.warning("Scrape failed for %s account %s", airline, account.account_id, exc_info=True)
            store.mark_cooldown(account.account_id)
            await session_mgr.invalidate_session(account.account_id)
        finally:
            await browser.close()

    return results


# ---------------------------------------------------------------------------
# United Airlines (MileagePlus)
# ---------------------------------------------------------------------------

async def _login_united(page: Any, account: LoyaltyAccount) -> bool:
    from smart_travel.accounts.sessions import _human_delay, _type_humanlike
    try:
        await page.goto("https://www.united.com/en/us/login", wait_until="domcontentloaded")
        await _human_delay(1000, 2000)
        await _type_humanlike(page, "#accountName", account.email)
        await _type_humanlike(page, "#password", account.password)
        await _human_delay(300, 800)
        for selector in ['button[data-id="btn-login"]', 'button[type="submit"]', '#btn-login']:
            try:
                await page.click(selector, timeout=3000)
                break
            except Exception:
                continue
        await page.wait_for_load_state("domcontentloaded")
        await _human_delay(1500, 2500)
        return await _verify_united_login(page)
    except Exception:
        logger.warning("United login failed", exc_info=True)
        return False


async def _verify_united_login(page: Any) -> bool:
    url = page.url
    if "/myaccount/" in url or "/account/" in url:
        return True
    for selector in [".header-account-name", ".account-name", '[data-test="account-name"]']:
        try:
            el = await page.query_selector(selector)
            if el:
                return True
        except Exception:
            pass
    return False


async def search_united_awards(
    origin: str, dest: str, date: str, cabin: str
) -> list[AwardResult]:
    """Search United MileagePlus award availability using pool rotation."""
    return await _search_airline_awards(
        airline="united", program="MileagePlus",
        login_fn=_login_united, verify_fn=_verify_united_login,
        scrape_fn=_scrape_united_page,
        origin=origin, dest=dest, date=date, cabin=cabin,
    )


async def _scrape_united_page(
    page: Any, origin: str, dest: str, date: str, cabin: str
) -> list[AwardResult]:
    """Navigate to United award search and scrape results."""
    award_url = (
        f"https://www.united.com/ual/en/us/flight-search/book-a-flight"
        f"?f={origin}&t={dest}&d={date}&tt=1&at=1&sc=7&taxng=1&newHP=True"
    )
    await page.goto(award_url, wait_until="domcontentloaded")
    await asyncio.sleep(3)
    body_text = await page.evaluate("() => document.body.innerText")

    if _is_bot_challenge(page.url, body_text):
        return [AwardResult(
            airline="united", program="MileagePlus",
            origin=origin, destination=dest, date=date, cabin=cabin,
            points=0, taxes_usd=0.0, availability="error",
            source_url=award_url, notes="bot challenge detected",
        )]

    parsed = await _scrape_united_results(page, origin, dest, date, award_url)
    if parsed:
        return parsed

    # Fallback: regex on page text
    for m in re.finditer(r"([\d,]+)\s*miles?", body_text, re.I):
        pts = _parse_points(m.group(1))
        if pts > 0:
            return [AwardResult(
                airline="united", program="MileagePlus",
                origin=origin, destination=dest, date=date, cabin=cabin,
                points=pts, taxes_usd=0.0, availability="available",
                source_url=award_url, notes="text fallback",
            )]
    return []


async def _scrape_united_results(
    page: Any, origin: str, dest: str, date: str, source_url: str
) -> list[AwardResult]:
    """Attempt to extract structured award results from United's DOM."""
    results = []
    try:
        await page.wait_for_selector(
            ".flight-stops, .segmentListing, .mileage-amount, [data-test='award-results']",
            timeout=12000,
        )
        # Extract all miles amounts visible on page
        elements = await page.query_selector_all(".mileage-amount, .award-price")
        for el in elements[:6]:  # cap at 6 results
            text = await el.inner_text()
            pts = _parse_points(text)
            if pts > 0:
                results.append(AwardResult(
                    airline="united", program="MileagePlus",
                    origin=origin, destination=dest, date=date, cabin="economy",
                    points=pts, taxes_usd=5.60, availability="available",
                    source_url=source_url,
                ))
    except Exception:
        pass
    return results


# ---------------------------------------------------------------------------
# Alaska Airlines (Mileage Plan)
# ---------------------------------------------------------------------------

async def _login_alaska(page: Any, account: LoyaltyAccount) -> bool:
    from smart_travel.accounts.sessions import _human_delay, _type_humanlike
    try:
        await page.goto("https://www.alaskaair.com/account/login", wait_until="domcontentloaded")
        await _human_delay(1000, 2000)
        for selector in ["#signIn_userName", "#username", 'input[type="email"]']:
            try:
                await _type_humanlike(page, selector, account.email)
                break
            except Exception:
                continue
        for selector in ["#signIn_password", "#password", 'input[type="password"]']:
            try:
                await _type_humanlike(page, selector, account.password)
                break
            except Exception:
                continue
        await _human_delay(300, 700)
        for selector in ["#btnSignIn", 'button[type="submit"]', ".btn-login"]:
            try:
                await page.click(selector, timeout=3000)
                break
            except Exception:
                continue
        await page.wait_for_load_state("domcontentloaded")
        await _human_delay(1500, 2500)
        return await _verify_alaska_login(page)
    except Exception:
        logger.warning("Alaska login failed", exc_info=True)
        return False


async def _verify_alaska_login(page: Any) -> bool:
    url = page.url
    if "/account/" in url and "login" not in url:
        return True
    for selector in [".user-name", ".account-greeting", '[data-test="user-name"]']:
        try:
            el = await page.query_selector(selector)
            if el:
                return True
        except Exception:
            pass
    return False


async def search_alaska_awards(
    origin: str, dest: str, date: str, cabin: str
) -> list[AwardResult]:
    """Search Alaska Mileage Plan award availability using pool rotation."""
    return await _search_airline_awards(
        airline="alaska", program="Mileage Plan",
        login_fn=_login_alaska, verify_fn=_verify_alaska_login,
        scrape_fn=_scrape_alaska_page,
        origin=origin, dest=dest, date=date, cabin=cabin,
    )


async def _scrape_alaska_page(
    page: Any, origin: str, dest: str, date: str, cabin: str
) -> list[AwardResult]:
    date_ak = _date_to_mmddyyyy(date)
    award_url = (
        f"https://www.alaskaair.com/booking/select-flight"
        f"?O={origin}&D={dest}&D1={date_ak}&OW=true&UPG=0&M=Award"
    )
    await page.goto(award_url, wait_until="domcontentloaded")
    await asyncio.sleep(3)
    body_text = await page.evaluate("() => document.body.innerText")

    if _is_bot_challenge(page.url, body_text):
        return [AwardResult(
            airline="alaska", program="Mileage Plan",
            origin=origin, destination=dest, date=date, cabin=cabin,
            points=0, taxes_usd=0.0, availability="error",
            source_url=award_url, notes="bot challenge detected",
        )]

    parsed = await _scrape_alaska_results(page, origin, dest, date, award_url)
    if parsed:
        return parsed

    for m in re.finditer(r"([\d,]+)\s*miles?", body_text, re.I):
        pts = _parse_points(m.group(1))
        if pts > 0:
            return [AwardResult(
                airline="alaska", program="Mileage Plan",
                origin=origin, destination=dest, date=date, cabin=cabin,
                points=pts, taxes_usd=0.0, availability="available",
                source_url=award_url, notes="text fallback",
            )]
    return []


async def _scrape_alaska_results(
    page: Any, origin: str, dest: str, date: str, source_url: str
) -> list[AwardResult]:
    results = []
    try:
        await page.wait_for_selector(
            "[data-testid='flight-results'], .flights-list, [data-miles], .fare-miles",
            timeout=12000,
        )
        elements = await page.query_selector_all("[data-miles], .fare-miles, .award-fare-amount")
        for el in elements[:6]:
            text = await el.inner_text()
            pts = _parse_points(text)
            if pts > 0:
                results.append(AwardResult(
                    airline="alaska", program="Mileage Plan",
                    origin=origin, destination=dest, date=date, cabin="economy",
                    points=pts, taxes_usd=5.60, availability="available",
                    source_url=source_url,
                ))
    except Exception:
        pass
    return results


# ---------------------------------------------------------------------------
# Delta Air Lines (SkyMiles)
# ---------------------------------------------------------------------------

async def _login_delta(page: Any, account: LoyaltyAccount) -> bool:
    from smart_travel.accounts.sessions import _human_delay, _type_humanlike
    try:
        await page.goto(
            "https://www.delta.com/us/en/sign-in/overview",
            wait_until="domcontentloaded",
        )
        await _human_delay(1500, 3000)  # Delta has aggressive bot detection
        for selector in ["#userId", "#username", 'input[name="userId"]']:
            try:
                # Delta prefers SkyMiles number
                value = account.loyalty_number or account.email
                await _type_humanlike(page, selector, value)
                break
            except Exception:
                continue
        for selector in ["#password", 'input[type="password"]']:
            try:
                await _type_humanlike(page, selector, account.password)
                break
            except Exception:
                continue
        await _human_delay(500, 1000)
        for selector in ["#loginButton", 'button[type="submit"]', ".login-btn"]:
            try:
                await page.click(selector, timeout=3000)
                break
            except Exception:
                continue
        await page.wait_for_load_state("networkidle")
        await _human_delay(1500, 2500)
        return await _verify_delta_login(page)
    except Exception:
        logger.warning("Delta login failed", exc_info=True)
        return False


async def _verify_delta_login(page: Any) -> bool:
    url = page.url
    if "/my-trips/" in url or "/myprofile/" in url:
        return True
    for selector in [".member-name", ".sky-miles-number", '[data-test="member-name"]']:
        try:
            el = await page.query_selector(selector)
            if el:
                return True
        except Exception:
            pass
    return False


async def search_delta_awards(
    origin: str, dest: str, date: str, cabin: str
) -> list[AwardResult]:
    """Search Delta SkyMiles award availability using pool rotation."""
    return await _search_airline_awards(
        airline="delta", program="SkyMiles",
        login_fn=_login_delta, verify_fn=_verify_delta_login,
        scrape_fn=_scrape_delta_page,
        origin=origin, dest=dest, date=date, cabin=cabin,
    )


async def _scrape_delta_page(
    page: Any, origin: str, dest: str, date: str, cabin: str
) -> list[AwardResult]:
    await page.goto(
        "https://www.delta.com/us/en/book-a-trip/flights",
        wait_until="domcontentloaded",
    )
    await asyncio.sleep(2)
    body_text = await page.evaluate("() => document.body.innerText")

    if _is_bot_challenge(page.url, body_text):
        return [AwardResult(
            airline="delta", program="SkyMiles",
            origin=origin, destination=dest, date=date, cabin=cabin,
            points=0, taxes_usd=0.0, availability="error",
            source_url=page.url, notes="bot challenge detected",
        )]

    return await _scrape_delta_via_form(page, origin, dest, date, cabin, page.url)


async def _scrape_delta_via_form(
    page: Any, origin: str, dest: str, date: str, cabin: str, source_url: str
) -> list[AwardResult]:
    results = []
    try:
        # Click award miles radio
        for selector in ['input[id="miles"]', '.award-checkbox', '[data-testid="award-radio"]']:
            try:
                await page.click(selector, timeout=3000)
                break
            except Exception:
                continue

        # Fill origin with autocomplete handling
        for selector in ["#fromAirportName", "#departureCity", 'input[aria-label*="from" i]']:
            try:
                await page.fill(selector, origin)
                await asyncio.sleep(1)
                # Pick first autocomplete result
                await page.keyboard.press("ArrowDown")
                await page.keyboard.press("Enter")
                break
            except Exception:
                continue

        # Fill destination
        for selector in ["#toAirportName", "#arrivalCity", 'input[aria-label*="to" i]']:
            try:
                await page.fill(selector, dest)
                await asyncio.sleep(1)
                await page.keyboard.press("ArrowDown")
                await page.keyboard.press("Enter")
                break
            except Exception:
                continue

        # Fill date
        for selector in ['input[aria-label="Depart"]', ".calendarTrigger", "#departureDate"]:
            try:
                await page.fill(selector, date)
                break
            except Exception:
                continue

        # Submit
        for selector in [".btn-search-submit", 'button[type="submit"]', "#submitBtn"]:
            try:
                await page.click(selector, timeout=3000)
                break
            except Exception:
                continue

        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)

        # Scrape results
        for sel in [".award-miles-amount", ".js-award-price", ".miles-price"]:
            elements = await page.query_selector_all(sel)
            for el in elements[:6]:
                text = await el.inner_text()
                pts = _parse_points(text)
                if pts > 0:
                    results.append(AwardResult(
                        airline="delta", program="SkyMiles",
                        origin=origin, destination=dest, date=date, cabin=cabin,
                        points=pts, taxes_usd=5.60, availability="available",
                        source_url=source_url,
                    ))
            if results:
                break

        # Text fallback
        if not results:
            body = await page.evaluate("() => document.body.innerText")
            for m in re.finditer(r"([\d,]+)\s*miles?", body, re.I):
                pts = _parse_points(m.group(1))
                if pts > 0:
                    results.append(AwardResult(
                        airline="delta", program="SkyMiles",
                        origin=origin, destination=dest, date=date, cabin=cabin,
                        points=pts, taxes_usd=0.0, availability="available",
                        source_url=source_url, notes="text fallback",
                    ))
                    break
    except Exception:
        logger.warning("Delta form scrape failed", exc_info=True)
    return results


# ---------------------------------------------------------------------------
# American Airlines (AAdvantage)
# ---------------------------------------------------------------------------

async def _login_aa(page: Any, account: LoyaltyAccount) -> bool:
    from smart_travel.accounts.sessions import _human_delay, _type_humanlike
    try:
        await page.goto(
            "https://www.aa.com/account/login/view",
            wait_until="domcontentloaded",
        )
        await _human_delay(1000, 2000)
        for selector in ["#aa-username", "#username", 'input[name="username"]']:
            try:
                await _type_humanlike(page, selector, account.email)
                break
            except Exception:
                continue
        for selector in ["#aa-password", "#password", 'input[type="password"]']:
            try:
                await _type_humanlike(page, selector, account.password)
                break
            except Exception:
                continue
        await _human_delay(300, 700)
        for selector in ["#loginSubmit", 'button[type="submit"]', ".btn-login"]:
            try:
                await page.click(selector, timeout=3000)
                break
            except Exception:
                continue
        await page.wait_for_load_state("domcontentloaded")
        await _human_delay(1500, 2500)
        # Check for bot challenge before verifying login
        body_text = await page.evaluate("() => document.body.innerText")
        if _is_bot_challenge(page.url, body_text):
            logger.warning("AA bot challenge on login page")
            return False
        return await _verify_aa_login(page)
    except Exception:
        logger.warning("AA login failed", exc_info=True)
        return False


async def _verify_aa_login(page: Any) -> bool:
    url = page.url
    if "/myaccount/" in url or "/my-trips/" in url:
        return True
    for selector in [".aadvantage-number", ".member-name", '[data-test="account-name"]']:
        try:
            el = await page.query_selector(selector)
            if el:
                return True
        except Exception:
            pass
    return False


async def search_aa_awards(
    origin: str, dest: str, date: str, cabin: str
) -> list[AwardResult]:
    """Search American Airlines AAdvantage award availability using pool rotation."""
    return await _search_airline_awards(
        airline="aa", program="AAdvantage",
        login_fn=_login_aa, verify_fn=_verify_aa_login,
        scrape_fn=_scrape_aa_page,
        origin=origin, dest=dest, date=date, cabin=cabin,
    )


async def _scrape_aa_page(
    page: Any, origin: str, dest: str, date: str, cabin: str
) -> list[AwardResult]:
    await page.goto(
        "https://www.aa.com/booking/find-flights",
        wait_until="domcontentloaded",
    )
    await asyncio.sleep(2)
    body_text = await page.evaluate("() => document.body.innerText")

    if _is_bot_challenge(page.url, body_text):
        return [AwardResult(
            airline="aa", program="AAdvantage",
            origin=origin, destination=dest, date=date, cabin=cabin,
            points=0, taxes_usd=0.0, availability="error",
            source_url=page.url, notes="bot challenge detected",
        )]

    return await _scrape_aa_via_form(page, origin, dest, date, cabin, page.url)


async def _scrape_aa_via_form(
    page: Any, origin: str, dest: str, date: str, cabin: str, source_url: str
) -> list[AwardResult]:
    results = []
    try:
        # Toggle award miles mode
        for selector in ['#award', 'input[value="miles"]', '[data-testid="award-toggle"]',
                          'label[for="milesAndPointsToggle"]']:
            try:
                await page.click(selector, timeout=3000)
                break
            except Exception:
                continue

        for selector in ["#aa-origin", "#departureCity", 'input[aria-label*="origin" i]']:
            try:
                await page.fill(selector, origin)
                await asyncio.sleep(0.8)
                await page.keyboard.press("ArrowDown")
                await page.keyboard.press("Enter")
                break
            except Exception:
                continue

        for selector in ["#aa-destination", "#arrivalCity", 'input[aria-label*="destination" i]']:
            try:
                await page.fill(selector, dest)
                await asyncio.sleep(0.8)
                await page.keyboard.press("ArrowDown")
                await page.keyboard.press("Enter")
                break
            except Exception:
                continue

        for selector in ["#aa-depart", "#departureDate", 'input[aria-label*="depart" i]']:
            try:
                await page.fill(selector, date)
                break
            except Exception:
                continue

        for selector in ["#searchFlights", 'button[type="submit"]', ".search-btn"]:
            try:
                await page.click(selector, timeout=3000)
                break
            except Exception:
                continue

        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(3)

        # Check for Distil/Imperva block
        body_text = await page.evaluate("() => document.body.innerText")
        if _is_bot_challenge(page.url, body_text):
            return []

        for sel in [".miles-amount", ".aa-award-miles", ".award-price-miles"]:
            elements = await page.query_selector_all(sel)
            for el in elements[:6]:
                text = await el.inner_text()
                pts = _parse_points(text)
                if pts > 0:
                    results.append(AwardResult(
                        airline="aa", program="AAdvantage",
                        origin=origin, destination=dest, date=date, cabin=cabin,
                        points=pts, taxes_usd=5.60, availability="available",
                        source_url=source_url,
                    ))
            if results:
                break

        if not results:
            for m in re.finditer(r"([\d,]+)\s*miles?", body_text, re.I):
                pts = _parse_points(m.group(1))
                if pts > 0:
                    results.append(AwardResult(
                        airline="aa", program="AAdvantage",
                        origin=origin, destination=dest, date=date, cabin=cabin,
                        points=pts, taxes_usd=0.0, availability="available",
                        source_url=source_url, notes="text fallback",
                    ))
                    break
    except Exception:
        logger.warning("AA form scrape failed", exc_info=True)
    return results


# ---------------------------------------------------------------------------
# Airline dispatch map
# ---------------------------------------------------------------------------

_AIRLINE_SEARCH_FNS = {
    "united": search_united_awards,
    "alaska": search_alaska_awards,
    "delta": search_delta_awards,
    "aa": search_aa_awards,
    "american": search_aa_awards,
}


# ---------------------------------------------------------------------------
# Top-level MCP tool
# ---------------------------------------------------------------------------

@tool(
    "search_awards",
    "Search award/points prices for a flight route across all major airlines. "
    "First discovers which airlines operate the route, then logs into each "
    "airline's loyalty program website to check award availability. "
    "Account pool management (registration, rotation, cooldowns) is handled "
    "automatically — no user action required.",
    {
        "origin": str,       # IATA airport code e.g. "SEA"
        "destination": str,  # IATA airport code e.g. "IAH"
        "date": str,         # "YYYY-MM-DD" or "MM/DD/YYYY"
        "cabin": str,        # optional: "economy", "business", "first"
    },
)
async def search_awards_tool(args: dict) -> dict:
    """Two-step award search with transparent pool management.

    1. Discover airlines on the route.
    2. For each airline: ensure pool has accounts (auto-register if needed),
       then search with LRU rotation.
    """
    origin: str = args.get("origin", "").upper().strip()
    destination: str = args.get("destination", "").upper().strip()
    date_raw: str = args.get("date", "").strip()
    cabin: str = args.get("cabin", "economy").lower().strip() or "economy"

    if not origin:
        return {"content": [{"type": "text", "text": "Error: 'origin' is required."}]}
    if not destination:
        return {"content": [{"type": "text", "text": "Error: 'destination' is required."}]}
    if not date_raw:
        return {"content": [{"type": "text", "text": "Error: 'date' is required."}]}

    date = _normalize_date(date_raw)

    # Step 1: Find airlines on this route
    airlines = await _find_airlines_for_route(origin, destination, date)

    # Step 2: Ensure pool + run scrapers concurrently
    from smart_travel.accounts.registration import ensure_pool_minimum, register_account

    store = get_account_store()
    sem = asyncio.Semaphore(3)
    failed_registration: list[str] = []
    tasks = []
    task_airlines = []

    for airline in airlines:
        fn = _AIRLINE_SEARCH_FNS.get(airline)
        if fn is None:
            continue

        # Auto-ensure pool has accounts for this airline
        if not store.get_next_account(airline):
            try:
                acct = await register_account(airline)
                if not acct:
                    failed_registration.append(airline)
                    continue
            except Exception:
                logger.warning("Auto-registration failed for %s", airline, exc_info=True)
                failed_registration.append(airline)
                continue

        async def _run(fn=fn, airline=airline):
            async with sem:
                return await fn(origin, destination, date, cabin)

        tasks.append(_run())
        task_airlines.append(airline)

    all_results: list[AwardResult] = []
    if tasks:
        raw = await asyncio.gather(*tasks, return_exceptions=True)
        for airline, res in zip(task_airlines, raw):
            if isinstance(res, Exception):
                logger.warning("Award search failed for %s: %s", airline, res)
                prog = _PROGRAM_NAMES.get(airline, airline.title())
                all_results.append(AwardResult(
                    airline=airline, program=prog,
                    origin=origin, destination=destination, date=date, cabin=cabin,
                    points=0, taxes_usd=0.0, availability="error",
                    source_url="", notes=f"scrape error: {res}",
                ))
            else:
                all_results.extend(res)

    # Step 3: Format results
    return {"content": [{"type": "text", "text": _format_results(
        all_results, origin, destination, date, failed_registration,
    )}]}


def _format_results(
    results: list[AwardResult],
    origin: str,
    dest: str,
    date: str,
    skipped: list[str],
) -> str:
    lines = [f"Award prices for {origin} -> {dest} on {date}:\n"]

    available = [r for r in results if r.availability not in ("error", "none") and r.points > 0]
    errors = [r for r in results if r.availability == "error"]

    if available:
        lines.append("| Airline | Program | Cabin | Points | Taxes/Fees | Notes |")
        lines.append("|---------|---------|-------|--------|------------|-------|")
        for r in sorted(available, key=lambda x: x.points):
            lines.append(
                f"| {r.airline.title()} | {r.program} | {r.cabin.title()} "
                f"| {r.points:,} | ${r.taxes_usd:.2f} | {r.notes} |"
            )
    else:
        lines.append("No award availability found with configured accounts.")

    if errors:
        lines.append("\nIssues encountered:")
        for r in errors:
            lines.append(f"- {r.airline.title()} ({r.program}): {r.notes}")

    if skipped:
        lines.append("\nCould not acquire accounts for:")
        for a in skipped:
            lines.append(f"- {a.title()} (auto-registration failed or not supported)")

    return "\n".join(lines)
