"""Ticketmaster Discovery API — event/ticket cash prices.

Uses ``/discovery/v2/events.json`` to search for concerts, sports,
theater, and other events.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from smart_travel.config import TicketmasterConfig
from smart_travel.data.sources.base import (
    BaseTicketSource,
    FetchMethod,
    PriceType,
    SourceInfo,
)

logger = logging.getLogger(__name__)

# Maps our event types → Ticketmaster classificationName values
_EVENT_TYPE_MAP: dict[str, str] = {
    "concert": "music",
    "sports": "sports",
    "theater": "arts & theatre",
    "museum": "arts & theatre",
}

_CITY_TO_COUNTRYCODE: dict[str, str] = {
    "new york": "US", "los angeles": "US", "chicago": "US",
    "seattle": "US", "miami": "US", "dallas": "US",
    "atlanta": "US", "boston": "US", "denver": "US",
    "san francisco": "US", "honolulu": "US",
    "toronto": "CA",
    "london": "GB",
    "paris": "FR",
    "tokyo": "JP",
    "sydney": "AU",
    "singapore": "SG",
    "dubai": "AE",
    "hong kong": "HK",
    "bangkok": "TH",
    "seoul": "KR",
    "mumbai": "IN",
    "rome": "IT",
    "amsterdam": "NL",
    "frankfurt": "DE",
}


class TicketmasterSource(BaseTicketSource):
    """Fetches cash event/ticket prices from the Ticketmaster API."""

    info = SourceInfo(
        name="ticketmaster",
        domain="tickets",
        fetch_method=FetchMethod.API,
        price_types=frozenset({PriceType.CASH}),
        priority=10,
    )

    def __init__(self, config: TicketmasterConfig) -> None:
        self._config = config
        self._client: httpx.AsyncClient | None = None

    async def is_available(self) -> bool:
        return self._config.is_configured

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._config.base_url,
                timeout=30.0,
            )
        return self._client

    async def search_tickets(
        self,
        city: str,
        date_from: str,
        date_to: str,
        event_type: str | None = None,
        max_price: float | None = None,
        min_rating: float | None = None,
    ) -> list[dict[str, Any]]:
        client = self._ensure_client()

        params: dict[str, Any] = {
            "apikey": self._config.api_key,
            "city": city,
            "startDateTime": f"{date_from}T00:00:00Z",
            "endDateTime": f"{date_to}T23:59:59Z",
            "size": 50,
            "sort": "date,asc",
        }

        if event_type:
            classification = _EVENT_TYPE_MAP.get(event_type)
            if classification:
                params["classificationName"] = classification

        country = _CITY_TO_COUNTRYCODE.get(city.lower())
        if country:
            params["countryCode"] = country

        try:
            resp = await client.get("/events.json", params=params)
            resp.raise_for_status()
        except Exception:
            logger.exception("Ticketmaster search failed")
            return []

        body: dict[str, Any] = resp.json()
        embedded = body.get("_embedded", {})
        raw_events: list[dict[str, Any]] = embedded.get("events", [])

        results: list[dict[str, Any]] = []
        for ev in raw_events:
            try:
                r = self._normalise(ev, city, event_type)
                if r is not None:
                    if (max_price is not None
                            and r["average_price_usd"] > max_price):
                        continue
                    if (min_rating is not None
                            and (r.get("rating") or 0) < min_rating):
                        continue
                    results.append(r)
            except Exception:
                logger.debug("Skipping unparseable TM event", exc_info=True)

        results.sort(key=lambda r: (r["date"], r["time"]))
        return results

    @staticmethod
    def _normalise(
        ev: dict[str, Any],
        city: str,
        event_type_hint: str | None,
    ) -> dict[str, Any] | None:
        name = ev.get("name", "")

        # Dates
        dates = ev.get("dates", {}).get("start", {})
        date = dates.get("localDate", "")
        time_ = dates.get("localTime", "")[:5] if dates.get("localTime") else ""

        # Venue
        venues = ev.get("_embedded", {}).get("venues", [])
        venue_name = venues[0]["name"] if venues else ""

        # Classifications → event type
        classifications = ev.get("classifications", [])
        resolved_type = event_type_hint or "other"
        if classifications:
            seg = classifications[0].get("segment", {}).get("name", "").lower()
            if "music" in seg:
                resolved_type = "concert"
            elif "sport" in seg:
                resolved_type = "sports"
            elif "art" in seg or "theatre" in seg or "theater" in seg:
                resolved_type = "theater"

        # Price range
        price_ranges = ev.get("priceRanges", [])
        if price_ranges:
            pr = price_ranges[0]
            price_min = float(pr.get("min", 0))
            price_max = float(pr.get("max", 0))
        else:
            return None  # no pricing info → skip

        avg = round((price_min + price_max) / 2, 2)

        url = ev.get("url", "")

        return {
            "source": "ticketmaster",
            "name": name,
            "event_type": resolved_type,
            "venue": venue_name,
            "city": city,
            "date": date,
            "time": time_,
            "price_range_usd": {"min": price_min, "max": price_max},
            "average_price_usd": avg,
            "tickets_available": None,
            "rating": None,
            "url": url,
        }
