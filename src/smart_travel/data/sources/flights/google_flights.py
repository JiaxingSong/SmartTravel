"""Google Flights browser source.

Uses Playwright to scrape flight results from Google Flights.
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


class GoogleFlightsSource(BaseFlightSource):
    """Scrapes flight results from Google Flights via Playwright."""

    info = SourceInfo(
        name="google_flights",
        domain="flights",
        fetch_method=FetchMethod.BROWSER,
        price_types=frozenset({PriceType.CASH}),
        priority=20,
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
        """Scrape Google Flights for results."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("Playwright not installed — skipping Google Flights")
            return []

        results: list[dict[str, Any]] = []
        url = self._build_url(origin, destination, departure_date, return_date, cabin_class)

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

                # Wait for flight results to render
                try:
                    await page.wait_for_selector(
                        "[data-test-id='offer-listing'], .pIav2d, .Rk10dc",
                        timeout=15000,
                    )
                except Exception:
                    logger.debug("Google Flights: no flight results rendered")

                # Extract flight data via DOM parsing
                raw = await page.evaluate("""
                    () => {
                        const cards = document.querySelectorAll(
                            '.pIav2d, [data-test-id="offer-listing"], .Rk10dc'
                        );
                        const results = [];
                        for (const card of cards) {
                            try {
                                const price = card.querySelector(
                                    '.YMlIz, [data-test-id="price"]'
                                )?.textContent?.trim() || '';
                                const airline = card.querySelector(
                                    '.Ir0Voe .sSHqwe, .c_cgZb .sSHqwe'
                                )?.textContent?.trim() || '';
                                const times = card.querySelector(
                                    '.Ir0Voe span, .mv1WYe span'
                                )?.textContent?.trim() || '';
                                const duration = card.querySelector(
                                    '.gvkrdb, .Ak5kof'
                                )?.textContent?.trim() || '';
                                const stops = card.querySelector(
                                    '.EfT7Ae span, .BbR8Ec'
                                )?.textContent?.trim() || '';
                                if (price) {
                                    results.push({
                                        price, airline, times, duration, stops
                                    });
                                }
                            } catch (e) {}
                        }
                        return results.slice(0, 20);
                    }
                """)

                results = self._parse_results(
                    raw, origin, destination, departure_date,
                    cabin_class, passengers, max_price, max_stops,
                )

                await browser.close()

        except Exception:
            logger.warning("Google Flights scraping failed", exc_info=True)

        return results

    def _build_url(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None,
        cabin_class: str,
    ) -> str:
        """Build a Google Flights search URL."""
        # Use first 3 chars uppercase as IATA guess
        orig = origin.upper()[:3] if len(origin) <= 3 else origin
        dest = destination.upper()[:3] if len(destination) <= 3 else destination

        cabin_map = {
            "economy": "1",
            "premium_economy": "2",
            "business": "3",
            "first": "4",
        }
        cabin_code = cabin_map.get(cabin_class, "1")

        base = f"https://www.google.com/travel/flights?q=Flights+from+{orig}+to+{dest}"
        base += f"+on+{departure_date}"
        if return_date:
            base += f"+return+{return_date}"
        base += f"&curr=USD&tfs=CAE&tfc={cabin_code}"
        return base

    def _parse_results(
        self,
        raw: list[dict[str, str]],
        origin: str,
        destination: str,
        departure_date: str,
        cabin_class: str,
        passengers: int,
        max_price: float | None,
        max_stops: int | None,
    ) -> list[dict[str, Any]]:
        """Convert raw scraped data to FlightResult dicts."""
        results: list[dict[str, Any]] = []

        for item in raw:
            price_text = item.get("price", "")
            price_match = re.search(r"[\d,]+", price_text.replace(",", ""))
            if not price_match:
                continue
            price = float(price_match.group().replace(",", ""))

            if max_price and price > max_price:
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

            total_price = price * passengers

            results.append({
                "source": "google_flights",
                "flight_number": "",
                "airline": item.get("airline", ""),
                "origin": origin,
                "origin_airport": origin.upper()[:3],
                "destination": destination,
                "destination_airport": destination.upper()[:3],
                "date": departure_date,
                "departure_time": item.get("times", ""),
                "duration": item.get("duration", ""),
                "stops": stops,
                "cabin_class": cabin_class,
                "price_usd": round(price, 2),
                "total_price_usd": round(total_price, 2),
                "passengers": passengers,
                "seats_remaining": None,
                "points_price": None,
                "points_program": None,
                "booking_url": None,
            })

        results.sort(key=lambda r: r.get("price_usd") or float("inf"))
        return results

    async def close(self) -> None:
        pass
