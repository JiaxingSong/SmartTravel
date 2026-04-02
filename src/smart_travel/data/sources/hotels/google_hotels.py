"""Google Hotels browser source.

Uses Playwright to scrape hotel results from Google Hotels.
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
    BaseHotelSource,
    FetchMethod,
    PriceType,
    SourceInfo,
)

logger = logging.getLogger(__name__)

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


class GoogleHotelsSource(BaseHotelSource):
    """Scrapes hotel results from Google Hotels via Playwright."""

    info = SourceInfo(
        name="google_hotels",
        domain="hotels",
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

    async def search_hotels(
        self,
        city: str,
        check_in: str,
        check_out: str,
        guests: int = 1,
        rooms: int = 1,
        min_stars: int | None = None,
        max_price_per_night: float | None = None,
        required_amenities: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Scrape Google Hotels for results."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("Playwright not installed — skipping Google Hotels")
            return []

        results: list[dict[str, Any]] = []
        url = self._build_url(city, check_in, check_out, guests)

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=self._config.headless)
                context = await browser.new_context(
                    user_agent=random.choice(_USER_AGENTS),
                    viewport={"width": 1366, "height": 768},
                )
                await context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => false})"
                )
                page = await context.new_page()

                await page.goto(url, wait_until="domcontentloaded",
                                timeout=self._config.timeout_ms)
                await page.wait_for_timeout(random.randint(2000, 4000))

                try:
                    await page.wait_for_selector(
                        ".uaTTDe, [data-hotel-id], .kCsInf",
                        timeout=15000,
                    )
                except Exception:
                    logger.debug("Google Hotels: no hotel results rendered")

                raw = await page.evaluate("""
                    () => {
                        const cards = document.querySelectorAll(
                            '.uaTTDe, [data-hotel-id], .kCsInf'
                        );
                        const results = [];
                        for (const card of cards) {
                            try {
                                const name = card.querySelector(
                                    '.QT7m7, h2, .BgYkof'
                                )?.textContent?.trim() || '';
                                const price = card.querySelector(
                                    '.kixHKb span, .dv1Q3e, .MW1oTb'
                                )?.textContent?.trim() || '';
                                const rating = card.querySelector(
                                    '.KFi5wf, .fjUnOb'
                                )?.textContent?.trim() || '';
                                const stars = card.querySelector(
                                    '.QJMBSc, .aHPril'
                                )?.textContent?.trim() || '';
                                const amenities = card.querySelector(
                                    '.HlxIlc, .XX3dkb'
                                )?.textContent?.trim() || '';
                                if (name && price) {
                                    results.push({
                                        name, price, rating, stars, amenities
                                    });
                                }
                            } catch(e) {}
                        }
                        return results.slice(0, 20);
                    }
                """)

                results = self._parse_results(
                    raw, city, check_in, check_out, guests, rooms,
                    min_stars, max_price_per_night, required_amenities,
                )

                await browser.close()

        except Exception:
            logger.warning("Google Hotels scraping failed", exc_info=True)

        return results

    def _build_url(
        self,
        city: str,
        check_in: str,
        check_out: str,
        guests: int,
    ) -> str:
        """Build a Google Hotels search URL."""
        city_slug = city.replace(" ", "+")
        return (
            f"https://www.google.com/travel/hotels/{city_slug}"
            f"?q={city_slug}+hotels"
            f"&dates={check_in}%2C{check_out}"
            f"&guests={guests}&curr=USD"
        )

    def _parse_results(
        self,
        raw: list[dict[str, str]],
        city: str,
        check_in: str,
        check_out: str,
        guests: int,
        rooms: int,
        min_stars: int | None,
        max_price_per_night: float | None,
        required_amenities: list[str] | None,
    ) -> list[dict[str, Any]]:
        """Convert raw scraped data to HotelResult dicts."""
        results: list[dict[str, Any]] = []

        # Calculate nights
        try:
            from datetime import date as dt_date
            ci = dt_date.fromisoformat(check_in)
            co = dt_date.fromisoformat(check_out)
            total_nights = max((co - ci).days, 1)
        except (ValueError, TypeError):
            total_nights = 1

        for item in raw:
            price_text = item.get("price", "")
            price_match = re.search(r"[\d,]+", price_text.replace(",", ""))
            if not price_match:
                continue
            price_per_night = float(price_match.group().replace(",", ""))

            if max_price_per_night and price_per_night > max_price_per_night:
                continue

            # Parse star rating
            stars_text = item.get("stars", "")
            stars_match = re.search(r"(\d)", stars_text)
            star_rating = int(stars_match.group(1)) if stars_match else 3

            if min_stars and star_rating < min_stars:
                continue

            # Parse guest rating
            rating_text = item.get("rating", "")
            rating_match = re.search(r"([\d.]+)", rating_text)
            guest_rating = float(rating_match.group(1)) if rating_match else None

            # Parse amenities
            amenities_text = item.get("amenities", "")
            amenities = [a.strip() for a in amenities_text.split(",") if a.strip()][:8]

            if required_amenities:
                found = {a.lower() for a in amenities}
                if not all(r.lower() in found for r in required_amenities):
                    continue

            total_price = price_per_night * total_nights * rooms

            results.append({
                "source": "google_hotels",
                "name": item.get("name", ""),
                "city": city,
                "neighborhood": "",
                "star_rating": star_rating,
                "guest_rating": guest_rating,
                "review_count": None,
                "price_per_night_usd": round(price_per_night, 2),
                "total_price_usd": round(total_price, 2),
                "total_nights": total_nights,
                "check_in": check_in,
                "check_out": check_out,
                "guests": guests,
                "rooms": rooms,
                "amenities": amenities,
                "cancellation_policy": "",
                "rooms_available": None,
                "points_price": None,
                "points_program": None,
            })

        results.sort(key=lambda r: r.get("price_per_night_usd") or float("inf"))
        return results

    async def close(self) -> None:
        pass
