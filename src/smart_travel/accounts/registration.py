"""Autonomous airline loyalty account registration via browser automation.

When the account pool has no available accounts for an airline, SmartTravel
can register a new one automatically using Playwright. This is entirely
transparent to the user — the agent silently acquires accounts as needed.

Uses a self-managed Outlook.com email account (see email_manager.py).
Falls back to POOL_BASE_EMAIL if set as an env var.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import string
import uuid
from typing import Any

from smart_travel.accounts.sessions import _human_delay, _type_humanlike, _USER_AGENT
from smart_travel.accounts.store import LoyaltyAccount, get_account_store, _PROGRAM_NAMES

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_FIRST_NAMES = [
    "James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael",
    "Linda", "David", "Elizabeth", "William", "Barbara", "Richard", "Susan",
    "Joseph", "Jessica", "Thomas", "Sarah", "Christopher", "Karen",
]
_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Anderson", "Taylor", "Thomas",
    "Jackson", "White", "Harris", "Martin", "Thompson", "Moore", "Lee",
]
_US_ADDRESSES = [
    {"street": "123 Main St", "city": "Dallas", "state": "TX", "zip": "75201"},
    {"street": "456 Oak Ave", "city": "Seattle", "state": "WA", "zip": "98101"},
    {"street": "789 Pine Blvd", "city": "Houston", "state": "TX", "zip": "77001"},
    {"street": "321 Elm Dr", "city": "Phoenix", "state": "AZ", "zip": "85001"},
    {"street": "654 Maple Ln", "city": "Denver", "state": "CO", "zip": "80201"},
]


def _get_base_email() -> str | None:
    """Return the base email for airline registrations.

    Priority:
    1. POOL_BASE_EMAIL env var (explicit override)
    2. Self-managed Outlook.com email (from email_manager)
    """
    explicit = os.environ.get("POOL_BASE_EMAIL", "").strip()
    if explicit:
        return explicit
    # Try self-managed email
    from smart_travel.accounts.email_manager import get_email_manager
    mgr = get_email_manager()
    return mgr.email_address


def _get_min_accounts() -> int:
    return int(os.environ.get("POOL_MIN_ACCOUNTS", "2"))


# ---------------------------------------------------------------------------
# Credential generation
# ---------------------------------------------------------------------------

def generate_credentials(airline: str, base_email: str | None = None) -> tuple[str, str]:
    """Generate an email (using +tag addressing) and password for a new account.

    Returns (email, password). The email uses the base email with a
    +<airline>_<short_uuid> tag. If base_email is not provided, uses
    _get_base_email() which checks env var then self-managed email.
    """
    base = base_email or _get_base_email()
    if not base:
        raise ValueError(
            "No email available for airline registration. "
            "Set POOL_BASE_EMAIL or let the agent create one automatically."
        )
    tag = f"{airline}_{uuid.uuid4().hex[:8]}"
    local, domain = base.split("@", 1)
    email = f"{local}+{tag}@{domain}"

    # Generate password meeting common airline requirements:
    # 8-16 chars, uppercase + lowercase + digit + special
    pw_chars = (
        random.choices(string.ascii_uppercase, k=3)
        + random.choices(string.ascii_lowercase, k=5)
        + random.choices(string.digits, k=3)
        + random.choices("!@#$%", k=1)
    )
    random.shuffle(pw_chars)
    password = "".join(pw_chars)

    return email, password


def _random_name() -> tuple[str, str]:
    return random.choice(_FIRST_NAMES), random.choice(_LAST_NAMES)


def _random_address() -> dict[str, str]:
    return random.choice(_US_ADDRESSES)


# ---------------------------------------------------------------------------
# Per-airline registration flows
# ---------------------------------------------------------------------------

async def _register_with_browser(
    airline: str,
    enroll_url: str,
    fill_fn: Any,
) -> LoyaltyAccount | None:
    """Common wrapper: launch browser, navigate to enrollment, fill form, persist."""
    # Ensure we have a base email — create one if needed
    base_email = _get_base_email()
    if not base_email:
        logger.info("No base email available — attempting to create Outlook account")
        from smart_travel.accounts.email_manager import get_email_manager
        mgr = get_email_manager()
        managed = await mgr.get_or_create_email()
        if managed:
            base_email = managed.address
        else:
            logger.warning("Could not create email account — cannot register %s", airline)
            return None

    email, password = generate_credentials(airline, base_email=base_email)
    first, last = _random_name()
    address = _random_address()

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("Playwright not installed — cannot register account")
        return None

    try:
        from smart_travel.config import load_config
        config = load_config()

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=config.browser.headless,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            context = await browser.new_context(
                user_agent=_USER_AGENT,
                locale="en-US",
                timezone_id="America/Los_Angeles",
                viewport={"width": 1280, "height": 800},
            )
            # Apply stealth
            try:
                from smart_travel.accounts.sessions import _STEALTH_AVAILABLE
                if _STEALTH_AVAILABLE:
                    from playwright_stealth import Stealth
                    await Stealth().apply_stealth_async(context)
                else:
                    from smart_travel.accounts.sessions import _MINIMAL_STEALTH_SCRIPT
                    await context.add_init_script(_MINIMAL_STEALTH_SCRIPT)
            except Exception:
                pass

            page = await context.new_page()
            page.set_default_timeout(config.browser.timeout_ms)

            await page.goto(enroll_url, wait_until="domcontentloaded")
            await _human_delay(1500, 2500)

            loyalty_number = await fill_fn(
                page, email, password, first, last, address
            )
            await browser.close()

        if loyalty_number:
            store = get_account_store()
            acct = store.add_account(
                airline=airline,
                email=email,
                password=password,
                loyalty_number=loyalty_number,
                program_name=_PROGRAM_NAMES.get(airline, airline.title()),
            )
            logger.info(
                "Auto-registered %s account %s (loyalty #%s)",
                airline, acct.account_id, loyalty_number,
            )
            return acct
        else:
            logger.warning("Registration for %s completed but no loyalty number extracted", airline)
            return None

    except Exception:
        logger.warning("Auto-registration failed for %s", airline, exc_info=True)
        return None


async def _fill_united_enrollment(
    page: Any, email: str, password: str, first: str, last: str, address: dict
) -> str | None:
    """Fill United MileagePlus enrollment form. Returns loyalty number or None."""
    try:
        for sel, val in [
            ("#firstName", first),
            ("#lastName", last),
            ("#email", email),
            ("#confirmEmail", email),
            ("#password", password),
            ("#confirmPassword", password),
        ]:
            try:
                await _type_humanlike(page, sel, val)
            except Exception:
                pass

        # Address fields
        for sel, key in [
            ("#streetAddress, #address1", "street"),
            ("#city", "city"),
            ("#zipCode, #postalCode", "zip"),
        ]:
            try:
                await page.fill(sel.split(",")[0].strip(), address[key])
            except Exception:
                try:
                    await page.fill(sel.split(",")[1].strip(), address[key])
                except Exception:
                    pass

        # State dropdown
        try:
            await page.select_option("select#state, select#stateProvince", address["state"])
        except Exception:
            pass

        await _human_delay(500, 1000)

        # Submit
        for sel in ['button[type="submit"]', "#enrollSubmit", ".enroll-btn"]:
            try:
                await page.click(sel, timeout=5000)
                break
            except Exception:
                continue

        await page.wait_for_load_state("domcontentloaded")
        await _human_delay(2000, 4000)

        # Extract loyalty number from confirmation page
        body = await page.evaluate("() => document.body.innerText")
        import re
        m = re.search(r"(?:MileagePlus|member|number)[:\s#]*([A-Z]{2}\d{6,}|\d{6,})", body, re.I)
        return m.group(1) if m else None

    except Exception:
        logger.warning("United enrollment form fill failed", exc_info=True)
        return None


async def _fill_alaska_enrollment(
    page: Any, email: str, password: str, first: str, last: str, address: dict
) -> str | None:
    """Fill Alaska Atmos Rewards enrollment form. Returns loyalty number or None.

    Uses page.locator() which pierces Shadow DOM — required because Alaska
    uses Auro web components with shadow roots around all inputs.
    """
    try:
        await page.wait_for_timeout(5000)

        # Dismiss cookie banner if present
        try:
            await page.click('button:has-text("Dismiss")', timeout=3000)
            await _human_delay(500, 1000)
        except Exception:
            pass

        # Alaska uses Auro web components with Shadow DOM. The actual <input>
        # elements have class util_displayHiddenVisually (0x0 size). We must
        # use force=True to bypass Playwright's visibility check, then dispatch
        # events so the Auro components register the value change.
        async def _fill_auro(selector: str, value: str) -> None:
            loc = page.locator(selector).first
            await loc.fill(value, force=True)
            await loc.dispatch_event("input")
            await loc.dispatch_event("change")

        # First name
        await _fill_auro('input[name="firstName"]', first)
        await _human_delay(300, 600)

        # Last name
        await _fill_auro('input[name="lastName"]', last)
        await _human_delay(300, 600)

        # Date of birth — month select, day input, year input
        try:
            month = str(random.randint(1, 12))
            day = str(random.randint(1, 28))
            year = str(random.randint(1980, 1999))
            await page.locator('select').first.select_option(month, force=True)
            await _human_delay(200, 400)
            await _fill_auro('#day-input-input', day)
            await _human_delay(200, 400)
            await _fill_auro('#year-input-input', year)
            await _human_delay(200, 400)
        except Exception as e:
            logger.debug("DOB fill issue: %s", e)

        # Email
        await _fill_auro('#enrollment-email-input', email)
        await _human_delay(300, 600)

        # Zip code
        await _fill_auro('#enrollment-zipCode-input', address["zip"])
        await _human_delay(300, 600)

        # User ID (use email prefix, min 7 chars with at least 1 letter)
        user_id = email.split("@")[0][:20]
        await _fill_auro('input[name="userId"]', user_id)
        await _human_delay(300, 600)

        # Password
        await _fill_auro('#enrollment-password-input', password)
        await _human_delay(500, 1000)

        # Scroll down to submit button
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await _human_delay(500, 1000)

        # Submit — "Join Atmos Rewards" button
        for sel in [
            'button:has-text("Join Atmos")',
            'button:has-text("Join")',
            'auro-button:has-text("Join")',
            'button[type="submit"]',
        ]:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    break
            except Exception:
                continue

        # Wait for confirmation page
        await page.wait_for_load_state("domcontentloaded")
        await _human_delay(5000, 8000)

        body = await page.evaluate("() => document.body.innerText")
        import re

        # Look for Atmos / Mileage Plan number
        for pattern in [
            r"(?:Atmos|Mileage Plan|member|number|rewards)\s*#?\s*[:.]?\s*(\d{6,})",
            r"#\s*(\d{8,12})",
            r"(\d{9,12})",
        ]:
            m = re.search(pattern, body, re.I)
            if m:
                return m.group(1)

        # Check if success page
        if any(x in body.lower() for x in [
            "welcome", "congratulations", "successfully enrolled",
            "you're in", "atmos rewards member",
        ]):
            url = page.url
            num_match = re.search(r"(\d{9,12})", url)
            if num_match:
                return num_match.group(1)
            logger.warning("Alaska enrollment succeeded but number not found on page")
            return "PENDING"

        logger.warning("Alaska enrollment unclear — page text: %s", body[:500])
        return None

    except Exception:
        logger.warning("Alaska enrollment form fill failed", exc_info=True)
        return None


async def _fill_delta_enrollment(
    page: Any, email: str, password: str, first: str, last: str, address: dict
) -> str | None:
    try:
        for sel, val in [
            ("#firstName", first),
            ("#lastName", last),
            ("#emailAddress", email),
            ("#password", password),
            ("#confirmPassword, #reEnterPassword", password),
        ]:
            for s in sel.split(","):
                try:
                    await _type_humanlike(page, s.strip(), val)
                    break
                except Exception:
                    continue

        await _human_delay(500, 1000)
        for sel in ['button[type="submit"]', "#submitEnrollment", ".enroll-submit"]:
            try:
                await page.click(sel, timeout=5000)
                break
            except Exception:
                continue

        await page.wait_for_load_state("domcontentloaded")
        await _human_delay(2000, 4000)

        body = await page.evaluate("() => document.body.innerText")
        import re
        m = re.search(r"(?:SkyMiles|member|number)[:\s#]*(\d{6,})", body, re.I)
        return m.group(1) if m else None

    except Exception:
        logger.warning("Delta enrollment form fill failed", exc_info=True)
        return None


async def _fill_aa_enrollment(
    page: Any, email: str, password: str, first: str, last: str, address: dict
) -> str | None:
    try:
        for sel, val in [
            ("#firstName, #first-name", first),
            ("#lastName, #last-name", last),
            ("#emailAddress, #email", email),
            ("#password, #createPassword", password),
            ("#confirmPassword", password),
        ]:
            for s in sel.split(","):
                try:
                    await _type_humanlike(page, s.strip(), val)
                    break
                except Exception:
                    continue

        # Address
        for sel, key in [("#streetAddress, #address1", "street"), ("#city", "city"), ("#zip, #zipCode", "zip")]:
            for s in sel.split(","):
                try:
                    await page.fill(s.strip(), address[key])
                    break
                except Exception:
                    continue

        try:
            await page.select_option("select#state, select#stateProvince", address["state"])
        except Exception:
            pass

        await _human_delay(500, 1000)
        for sel in ['button[type="submit"]', "#enrollSubmit", ".enroll-btn"]:
            try:
                await page.click(sel, timeout=5000)
                break
            except Exception:
                continue

        await page.wait_for_load_state("domcontentloaded")
        await _human_delay(2000, 4000)

        body = await page.evaluate("() => document.body.innerText")
        import re
        m = re.search(r"(?:AAdvantage|member|number)[:\s#]*([A-Z]{2,3}\d{5,}|\d{6,})", body, re.I)
        return m.group(1) if m else None

    except Exception:
        logger.warning("AA enrollment form fill failed", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Public dispatch
# ---------------------------------------------------------------------------

_ENROLL_URLS: dict[str, str] = {
    "united": "https://www.united.com/en/us/mileageplus/enroll",
    "alaska": "https://www.alaskaair.com/atmosrewards/enroll/shortform",
    "delta": "https://www.delta.com/us/en/skymiles/enroll",
    "aa": "https://www.aa.com/loyalty/enrollment/enroll",
}

_FILL_FNS: dict[str, Any] = {
    "united": _fill_united_enrollment,
    "alaska": _fill_alaska_enrollment,
    "delta": _fill_delta_enrollment,
    "aa": _fill_aa_enrollment,
}


async def register_account(airline: str) -> LoyaltyAccount | None:
    """Attempt to auto-register a new loyalty account for the airline.

    Returns the new LoyaltyAccount (already persisted in the store), or None
    if registration failed. Transparent to the end user.
    """
    airline = airline.lower().strip()
    enroll_url = _ENROLL_URLS.get(airline)
    fill_fn = _FILL_FNS.get(airline)
    if not enroll_url or not fill_fn:
        logger.warning("No registration flow for airline: %s", airline)
        return None

    return await _register_with_browser(airline, enroll_url, fill_fn)


async def ensure_pool_minimum(airline: str) -> int:
    """Ensure the pool has at least POOL_MIN_ACCOUNTS active accounts.

    Registers new accounts as needed. Returns the number of active accounts
    after ensuring the minimum.
    """
    store = get_account_store()
    status = store.get_pool_status(airline)
    target = _get_min_accounts()
    needed = target - status["active"]

    registered = 0
    for _ in range(max(0, needed)):
        acct = await register_account(airline)
        if acct:
            registered += 1
        else:
            break  # Stop trying if registration fails

    if registered:
        logger.info(
            "Auto-registered %d new %s accounts (pool now %d active)",
            registered, airline, status["active"] + registered,
        )
    return status["active"] + registered
