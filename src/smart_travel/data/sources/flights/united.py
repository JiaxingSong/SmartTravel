"""United Airlines award flight browser source.

Uses Playwright to scrape award/miles flight results from United.com.
This is a slow/fragile source (priority 20) meant as a supplement to
API sources.  Results are cached by the resolver layer.

Requires: ``pip install playwright && playwright install chromium``
"""

from __future__ import annotations

import logging
import random
import re
from typing import Any

from smart_travel.config import BrowserConfig
from smart_travel.data.sources.base import (
    BaseFlightSource,
    FetchMethod,
    PriceType,
    SourceInfo,
)

logger = logging.getLogger(__name__)

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

_CITY_TO_IATA: dict[str, str] = {
    "new york": "EWR", "tokyo": "NRT", "london": "LHR",
    "paris": "CDG", "chicago": "ORD", "los angeles": "LAX",
    "san francisco": "SFO", "seattle": "SEA", "miami": "MIA",
    "toronto": "YYZ", "seoul": "ICN", "singapore": "SIN",
    "sydney": "SYD", "dubai": "DXB", "hong kong": "HKG",
    "bangkok": "BKK", "mumbai": "BOM", "delhi": "DEL",
    "amsterdam": "AMS", "frankfurt": "FRA", "rome": "FCO",
    "dallas": "DFW", "denver": "DEN", "atlanta": "ATL",
    "boston": "BOS", "honolulu": "HNL", "shanghai": "PVG",
    "beijing": "PEK", "houston": "IAH", "washington": "IAD",
}

_CABIN_MAP: dict[str, str] = {
    "economy": "7",
    "premium_economy": "3",
    "business": "2",
    "first": "1",
}


def _resolve_iata(city_or_code: str) -> str:
    """Convert city name or airport code to IATA code."""
    if len(city_or_code) == 3 and city_or_code.isalpha():
        return city_or_code.upper()
    return _CITY_TO_IATA.get(city_or_code.lower(), city_or_code[:3].upper())


class UnitedAwardSource(BaseFlightSource):
    """Scrapes award flight results from United.com via Playwright."""

    info = SourceInfo(
        name="united_award",
        domain="flights",
        fetch_method=FetchMethod.BROWSER,
        price_types=frozenset({PriceType.POINTS}),
        priority=20,
        airlines=frozenset({"UA"}),
    )

    def __init__(self, config: BrowserConfig) -> None:
        self._config = config

    async def is_available(self) -> bool:
        """Check that Playwright is installed."""
        try:
            import playwright  # noqa: F401
            return True
        except ImportError:
            return False

    async def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None = None,
        cabin_class: str = "economy",
        passengers: int = 1,
        max_price: float | None = None,
        max_stops: int | None = None,
    ) -> list[dict[str, Any]]:
        """Scrape United.com for award flight results."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("Playwright not installed — skipping United award search")
            return []

        results: list[dict[str, Any]] = []
        url = self._build_url(origin, destination, departure_date, cabin_class)

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=self._config.headless)
                context = await browser.new_context(
                    user_agent=random.choice(_USER_AGENTS),
                    viewport={"width": 1366, "height": 768},
                )
                # Anti-detection: remove webdriver flag
                await context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => false})"
                )
                page = await context.new_page()

                await page.goto(url, wait_until="domcontentloaded",
                                timeout=self._config.timeout_ms)

                # Random delay for natural loading
                await page.wait_for_timeout(random.randint(2000, 4000))

                # Wait for flight result cards to render
                try:
                    await page.wait_for_selector(
                        "[data-testid='flight-card'], .flight-result-card, "
                        ".app-components-Shopping-FlightCardContainer",
                        timeout=15000,
                    )
                except Exception:
                    logger.debug("United: no award flight results rendered")

                # Extract award flight data via DOM parsing
                raw = await page.evaluate("""
                    () => {
                        const selectors = [
                            '[data-testid="flight-card"]',
                            '.flight-result-card',
                            '.app-components-Shopping-FlightCardContainer'
                        ];
                        let cards = [];
                        for (const sel of selectors) {
                            cards = document.querySelectorAll(sel);
                            if (cards.length > 0) break;
                        }
                        const results = [];
                        for (const card of cards) {
                            try {
                                const miles = (
                                    card.querySelector('.award-miles, [data-testid="miles-price"], .amount-miles')
                                    ?.textContent?.trim() || ''
                                );
                                const airline = (
                                    card.querySelector('.airline-name, [data-testid="airline-name"], .carrier-name')
                                    ?.textContent?.trim() || 'United Airlines'
                                );
                                const flightNum = (
                                    card.querySelector('.flight-number, [data-testid="flight-number"]')
                                    ?.textContent?.trim() || ''
                                );
                                const times = (
                                    card.querySelector('.departure-time, [data-testid="departure-time"]')
                                    ?.textContent?.trim() || ''
                                );
                                const duration = (
                                    card.querySelector('.duration, [data-testid="duration"]')
                                    ?.textContent?.trim() || ''
                                );
                                const stops = (
                                    card.querySelector('.stops, [data-testid="stops"]')
                                    ?.textContent?.trim() || ''
                                );
                                if (miles) {
                                    results.push({
                                        miles, airline, flightNum, times, duration, stops
                                    });
                                }
                            } catch (e) {}
                        }
                        return results.slice(0, 20);
                    }
                """)

                results = self._parse_results(
                    raw, origin, destination, departure_date,
                    cabin_class, passengers, max_stops,
                )

                await browser.close()

        except Exception:
            logger.warning("United award scraping failed", exc_info=True)

        return results

    def _build_url(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        cabin_class: str,
    ) -> str:
        """Build a United.com award search URL."""
        orig = _resolve_iata(origin)
        dest = _resolve_iata(destination)
        cabin_code = _CABIN_MAP.get(cabin_class, "7")

        return (
            f"https://www.united.com/en/us/fsr/choose-flights"
            f"?f={orig}&t={dest}&d={departure_date}"
            f"&tt=1&at=1&sc={cabin_code}&px=1"
            f"&taxng=1&newHP=True&clm=7&st=bestmatches"
        )

    def _parse_results(
        self,
        raw: list[dict[str, str]],
        origin: str,
        destination: str,
        departure_date: str,
        cabin_class: str,
        passengers: int,
        max_stops: int | None,
    ) -> list[dict[str, Any]]:
        """Convert raw scraped data to FlightResult dicts."""
        results: list[dict[str, Any]] = []

        for item in raw:
            miles_text = item.get("miles", "")
            miles_match = re.search(r"[\d,]+", miles_text.replace(",", ""))
            if not miles_match:
                continue
            miles = int(miles_match.group().replace(",", ""))
            if miles == 0:
                continue

            # Parse stops
            stops_text = item.get("stops", "").lower()
            if "nonstop" in stops_text or "direct" in stops_text:
                stops = 0
            else:
                stops_match = re.search(r"(\d+)", stops_text)
                stops = int(stops_match.group(1)) if stops_match else 0

            if max_stops is not None and stops > max_stops:
                continue

            results.append({
                "source": "united_award",
                "flight_number": item.get("flightNum", ""),
                "airline": item.get("airline", "United Airlines"),
                "origin": origin,
                "origin_airport": _resolve_iata(origin),
                "destination": destination,
                "destination_airport": _resolve_iata(destination),
                "date": departure_date,
                "departure_time": item.get("times", ""),
                "duration": item.get("duration", ""),
                "stops": stops,
                "cabin_class": cabin_class,
                "passengers": passengers,
                "price_usd": None,
                "total_price_usd": None,
                "points_price": miles,
                "points_program": "united",
                "seats_remaining": None,
                "booking_url": None,
            })

        results.sort(key=lambda r: r.get("points_price") or float("inf"))
        return results

    async def close(self) -> None:
        pass
