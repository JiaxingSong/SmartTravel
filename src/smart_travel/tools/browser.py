"""General-purpose browser MCP tools for SmartTravel.

Implements web_search, open_page, fill_form, and monitor_price using
Playwright. All tools are registered via the @tool decorator from
claude_agent_sdk.
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from claude_agent_sdk import tool

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger(__name__)

# Realistic browser User-Agent — prevents headless detection on most sites
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Price monitor registry (module-level, in-memory)
# ---------------------------------------------------------------------------

@dataclass
class _MonitorJob:
    label: str
    url: str
    selector: str
    target_price: float
    check_interval_minutes: int
    last_checked: float = field(default_factory=time.time)
    triggered: bool = False
    triggered_value: str = ""


_monitors: list[_MonitorJob] = []
_pending_alerts: list[str] = []
_monitor_lock = threading.Lock()
_monitor_task_started = False


def get_pending_alerts() -> list[str]:
    """Return and clear all triggered monitor alerts."""
    with _monitor_lock:
        alerts = list(_pending_alerts)
        _pending_alerts.clear()
    return alerts


async def _new_page(pw, headless: bool, timeout_ms: int):  # type: ignore[no-untyped-def]
    """Launch a Chromium browser and return a configured page."""
    browser = await pw.chromium.launch(headless=headless)
    context = await browser.new_context(
        user_agent=_USER_AGENT,
        locale="en-US",
        timezone_id="America/Los_Angeles",
        viewport={"width": 1280, "height": 800},
    )
    page = await context.new_page()
    page.set_default_timeout(timeout_ms)
    return browser, page


async def _check_monitor_job(job: _MonitorJob) -> None:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return

    try:
        from smart_travel.config import load_config
        config = load_config()
        async with async_playwright() as pw:
            browser, page = await _new_page(pw, config.browser.headless, config.browser.timeout_ms)
            await page.goto(job.url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            element = await page.query_selector(job.selector)
            if element:
                text = await element.inner_text()
                price_match = re.search(r"[\d,]+\.?\d*", text.replace(",", ""))
                if price_match:
                    current = float(price_match.group().replace(",", ""))
                    with _monitor_lock:
                        job.last_checked = time.time()
                        if current <= job.target_price:
                            job.triggered = True
                            job.triggered_value = text.strip()
                            _pending_alerts.append(
                                f"Price alert '{job.label}': current price "
                                f"{text.strip()} is at or below your target "
                                f"${job.target_price:.2f}. Check: {job.url}"
                            )
            await browser.close()
    except Exception:
        logger.warning("Monitor check failed for %s", job.label, exc_info=True)
        with _monitor_lock:
            job.last_checked = time.time()


async def _run_monitors() -> None:
    """Continuously check registered price monitors."""
    while True:
        await asyncio.sleep(30)
        now = time.time()
        with _monitor_lock:
            jobs_due = [
                j for j in _monitors
                if not j.triggered
                and (now - j.last_checked) >= j.check_interval_minutes * 60
            ]
        for job in jobs_due:
            await _check_monitor_job(job)


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_PLAYWRIGHT_MISSING = {
    "content": [{
        "type": "text",
        "text": (
            "Playwright is not installed. "
            "Run: pip install smart-travel[browser] && playwright install chromium"
        ),
    }]
}

_PAGE_TRUNCATE_LIMIT = 8000


def _clean_page_text(text: str) -> str:
    """Collapse excessive blank lines and truncate."""
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > _PAGE_TRUNCATE_LIMIT:
        text = text[:_PAGE_TRUNCATE_LIMIT] + "\n... [truncated]"
    return text


# ---------------------------------------------------------------------------
# Browser tools
# ---------------------------------------------------------------------------

@tool(
    "web_search",
    "Search the web using a browser. Returns page titles, URLs, and text "
    "snippets from the top results. Use this to find travel sites, prices, "
    "availability, or any other travel-related information.",
    {"query": str, "max_results": int},
)
async def web_search_tool(args: dict) -> dict:
    """Search Bing and return titles, URLs, and snippets."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return _PLAYWRIGHT_MISSING

    query: str = args.get("query", "")
    max_results: int = int(args.get("max_results", 10))

    if not query:
        return {"content": [{"type": "text", "text": "No query provided."}]}

    try:
        from smart_travel.config import load_config
        config = load_config()
        search_url = f"https://www.bing.com/search?q={urllib.parse.quote_plus(query)}"

        async with async_playwright() as pw:
            browser, page = await _new_page(pw, config.browser.headless, config.browser.timeout_ms)
            await page.goto(search_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(1500)

            results = await page.evaluate("""
                () => {
                    const items = document.querySelectorAll('li.b_algo');
                    const out = [];
                    for (const item of items) {
                        const a = item.querySelector('h2 a');
                        const cite = item.querySelector('cite');
                        const snippet = item.querySelector('.b_caption p, .b_snippet, .b_algoSlug');
                        if (a) {
                            // cite text looks like "https://site.com \u203a path"
                            // extract just the base URL portion before the separator
                            const citeText = cite ? cite.innerText.trim().split('\u203a')[0].trim() : '';
                            const url = (citeText.startsWith('http') || citeText.startsWith('www'))
                                ? citeText
                                : a.href;
                            out.push({
                                title: a.innerText.trim(),
                                url: url,
                                snippet: snippet ? snippet.innerText.trim() : ''
                            });
                        }
                        if (out.length >= 20) break;
                    }
                    return out;
                }
            """)
            await browser.close()

        results = results[:max_results]
        if not results:
            return {"content": [{"type": "text", "text": f"No results found for: {query}"}]}

        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"Result {i}: {r['title']}")
            lines.append(f"URL: {r['url']}")
            if r.get("snippet"):
                lines.append(f"Snippet: {r['snippet']}")
            lines.append("")

        return {"content": [{"type": "text", "text": "\n".join(lines).strip()}]}

    except Exception as e:
        logger.warning("web_search failed", exc_info=True)
        return {"content": [{"type": "text", "text": f"Search failed: {e}"}]}


@tool(
    "open_page",
    "Open a URL in a browser and return the page's readable text content. "
    "Use this to read flight results, hotel listings, event pages, or any "
    "travel-related web page.",
    {"url": str},
)
async def open_page_tool(args: dict) -> dict:
    """Open a URL and return its cleaned text content."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return _PLAYWRIGHT_MISSING

    url: str = args.get("url", "")
    if not url:
        return {"content": [{"type": "text", "text": "No URL provided."}]}

    try:
        from smart_travel.config import load_config
        config = load_config()

        async with async_playwright() as pw:
            browser, page = await _new_page(pw, config.browser.headless, config.browser.timeout_ms)
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            text = await page.evaluate("() => document.body.innerText")
            await browser.close()

        return {"content": [{"type": "text", "text": _clean_page_text(text)}]}

    except Exception as e:
        logger.warning("open_page failed for %s", url, exc_info=True)
        return {"content": [{"type": "text", "text": f"Failed to open page: {e}"}]}


@tool(
    "fill_form",
    "Open a URL, fill in form fields by their visible label or input name, "
    "and optionally submit the form. Returns the resulting page content. "
    "Use this to search on specific travel sites like Google Flights, Kayak, "
    "Booking.com, etc.",
    {"url": str, "fields": dict, "submit": bool},
)
async def fill_form_tool(args: dict) -> dict:
    """Open a page, fill form fields, optionally submit, return page text."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return _PLAYWRIGHT_MISSING

    url: str = args.get("url", "")
    fields: dict[str, str] = args.get("fields", {})
    submit: bool = bool(args.get("submit", False))

    if not url:
        return {"content": [{"type": "text", "text": "No URL provided."}]}

    try:
        from smart_travel.config import load_config
        config = load_config()

        async with async_playwright() as pw:
            browser, page = await _new_page(pw, config.browser.headless, config.browser.timeout_ms)
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            for field_name, value in fields.items():
                filled = False
                for selector in [
                    f'[name="{field_name}"]',
                    f'[id="{field_name}"]',
                    f'[placeholder*="{field_name}" i]',
                ]:
                    try:
                        await page.fill(selector, str(value), timeout=3000)
                        filled = True
                        break
                    except Exception:
                        pass
                if not filled:
                    try:
                        await page.get_by_label(field_name).fill(str(value))
                    except Exception:
                        logger.debug("Could not fill field: %s", field_name)

            if submit:
                try:
                    await page.click('[type="submit"]', timeout=3000)
                except Exception:
                    await page.keyboard.press("Enter")
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(3000)

            text = await page.evaluate("() => document.body.innerText")
            await browser.close()

        return {"content": [{"type": "text", "text": _clean_page_text(text)}]}

    except Exception as e:
        logger.warning("fill_form failed for %s", url, exc_info=True)
        return {"content": [{"type": "text", "text": f"Failed to fill form: {e}"}]}


@tool(
    "monitor_price",
    "Register a background price monitor. Periodically opens a URL, checks "
    "a CSS selector for a price value, and alerts the user in the next "
    "conversation turn when the price drops to or below the target. "
    "The user will be notified the next time they send a message.",
    {
        "label": str,
        "url": str,
        "selector": str,
        "target_price": float,
        "check_interval_minutes": int,
    },
)
async def monitor_price_tool(args: dict) -> dict:
    """Register a background price monitor job."""
    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError:
        return _PLAYWRIGHT_MISSING

    label: str = args.get("label", "price watch")
    url: str = args.get("url", "")
    selector: str = args.get("selector", "")
    target_price: float = float(args.get("target_price", 0.0))
    check_interval_minutes: int = int(args.get("check_interval_minutes", 5))

    if not url or not selector:
        return {"content": [{"type": "text", "text": "Both 'url' and 'selector' are required."}]}

    job = _MonitorJob(
        label=label,
        url=url,
        selector=selector,
        target_price=target_price,
        check_interval_minutes=check_interval_minutes,
    )
    with _monitor_lock:
        _monitors.append(job)

    global _monitor_task_started
    if not _monitor_task_started:
        _monitor_task_started = True
        asyncio.create_task(_run_monitors())

    return {
        "content": [{
            "type": "text",
            "text": (
                f"Monitor registered: '{label}'. I will check {url} every "
                f"{check_interval_minutes} minute(s) and alert you when the "
                f"price reaches ${target_price:.2f} (selector: {selector})."
            ),
        }]
    }
