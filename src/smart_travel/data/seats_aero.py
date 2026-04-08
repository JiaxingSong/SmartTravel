"""Seats.aero scraper for real-time award availability.

Seats.aero is a free award search aggregator that shows actual points prices
across multiple loyalty programs. No login required for searches within 60 days.

The scraper navigates to seats.aero/search with URL parameters, waits for results,
and parses the table of availability data.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SeatsAeroResult:
    """A single award availability result from seats.aero."""
    date: str              # "2026-05-15"
    program: str           # "United", "Alaska", "Aeroplan"
    origin: str            # "SEA"
    destination: str       # "IAH"
    economy_pts: int       # 15000 (0 = not available)
    premium_pts: int       # 0 = not available
    business_pts: int      # 48900 (0 = not available)
    first_pts: int         # 0 = not available
    is_direct: bool        # True if nonstop
    last_seen: str         # "5 days ago", "19 hours ago"


async def search_seats_aero(
    origin: str,
    destination: str,
    date: str,
) -> list[SeatsAeroResult]:
    """Scrape seats.aero for real award availability on a route/date.

    Args:
        origin: IATA airport code
        destination: IATA airport code
        date: YYYY-MM-DD format

    Returns:
        List of SeatsAeroResult with actual points prices per program.
        Empty list if scraping fails or date is >60 days out (PRO required).
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("Playwright not installed")
        return []

    url = (
        f"https://seats.aero/search?"
        f"origin={origin.upper()}&destination={destination.upper()}&date={date}"
    )

    try:
        from smart_travel.config import load_config
        config = load_config()

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=config.browser.headless,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            page = await browser.new_page()
            page.set_default_timeout(config.browser.timeout_ms)

            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(10)  # seats.aero needs time to load results

            body = await page.evaluate("() => document.body.innerText")
            await browser.close()

        # Check for PRO-only message
        if "PRO accounts can search" in body or "aren't signed in" in body:
            logger.info("seats.aero: date >60 days out, PRO required")
            return []

        return _parse_seats_aero_results(body, origin, destination, date)

    except Exception:
        logger.warning("seats.aero scrape failed", exc_info=True)
        return []


def _parse_seats_aero_results(
    body: str,
    origin: str,
    destination: str,
    date: str,
) -> list[SeatsAeroResult]:
    """Parse seats.aero page text into structured results.

    The table format is:
    Date | Last Seen | Program | Departs | Arrives | Economy | Premium | Business | First
    2026-05-15 | 5 days ago | Alaska | SEA | IAH | 15,000 pts | Not Available | 35,000 pts | Not Available
    """
    results: list[SeatsAeroResult] = []

    lines = body.split("\n")
    for line in lines:
        line = line.strip()
        if not line or date not in line:
            continue

        # Look for lines with "pts" (award results)
        if "pts" not in line.lower() and "not available" not in line.lower():
            continue

        # Try to extract program name — it appears after the last_seen timestamp
        # Pattern: date \t last_seen \t program \t origin \t dest \t economy \t premium \t business \t first
        parts = re.split(r"\t+", line)
        if len(parts) < 6:
            # Try space-separated
            parts = re.split(r"\s{2,}", line)

        if len(parts) < 6:
            continue

        # Find which part is the program name
        program = ""
        for part in parts:
            part_clean = part.strip()
            if part_clean in (
                "Aeroplan", "Alaska", "United", "American", "Delta",
                "Azul", "Velocity", "Qantas", "ANA", "JAL",
                "British Airways", "Turkish", "LifeMiles", "Virgin Atlantic",
                "Air France", "KLM", "Singapore", "Korean Air", "Cathay Pacific",
                "Emirates", "Etihad", "Finnair", "Iberia", "TAP",
                "SAS", "SWISS", "Lufthansa", "Austrian",
            ):
                program = part_clean
                break

        if not program:
            # Try regex for known programs
            prog_match = re.search(
                r"(Aeroplan|Alaska|United|American|Delta|Azul|Velocity|Qantas|"
                r"ANA|JAL|British Airways|Turkish|LifeMiles|Virgin Atlantic|"
                r"Air France|KLM|Singapore|Korean Air|Cathay Pacific|"
                r"Emirates|Etihad|Finnair|Iberia|TAP|SAS|SWISS|Lufthansa|Austrian)",
                line,
            )
            if prog_match:
                program = prog_match.group(1)

        if not program:
            continue

        # Extract points for each cabin
        def _extract_pts(text: str, cabin_keyword: str = "") -> int:
            """Extract points value from text like '15,000 pts' or 'Not Available'."""
            pts_matches = re.findall(r"([\d,]+)\s*pts", text)
            if pts_matches:
                # Find the one associated with this context
                for m in pts_matches:
                    val = int(m.replace(",", ""))
                    if val > 0:
                        return val
            return 0

        # Parse points per cabin from the line
        # Look for patterns: "15,000 pts" followed by "Not Available" or another "XX,XXX pts"
        pts_pattern = r"([\d,]+)\s*pts|Not Available"
        cabin_values = re.findall(pts_pattern, line, re.I)

        economy = 0
        premium = 0
        business = 0
        first = 0

        # cabin_values are in order: economy, premium, business, first
        for idx, val in enumerate(cabin_values):
            pts = int(val.replace(",", "")) if val else 0
            if idx == 0:
                economy = pts
            elif idx == 1:
                premium = pts
            elif idx == 2:
                business = pts
            elif idx == 3:
                first = pts

        # Check if direct flight (bold text or specific marker)
        is_direct = "•" not in line  # seats.aero uses • for connections

        # Last seen
        seen_match = re.search(r"(\d+\s*(?:hours?|days?|minutes?)\s*ago)", line, re.I)
        last_seen = seen_match.group(1) if seen_match else ""

        if economy > 0 or business > 0 or first > 0:
            results.append(SeatsAeroResult(
                date=date,
                program=program,
                origin=origin.upper(),
                destination=destination.upper(),
                economy_pts=economy,
                premium_pts=premium,
                business_pts=business,
                first_pts=first,
                is_direct=is_direct,
                last_seen=last_seen,
            ))

    return results
