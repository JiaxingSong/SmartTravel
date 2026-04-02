"""Amadeus Flight Offers Search — cash prices via REST API.

Uses the `/v2/shopping/flight-offers`` endpoint to retrieve live
economy/business/first fares from the Amadeus GDS.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from smart_travel.config import AmadeusConfig
from smart_travel.data.sources._amadeus_auth import AmadeusTokenManager
from smart_travel.data.sources.base import (
    BaseFlightSource,
    FetchMethod,
    PriceType,
    SourceInfo,
)

logger = logging.getLogger(__name__)

# Amadeus cabin class mapping
_CABIN_MAP: dict[str, str] = {
    "economy": "ECONOMY",
    "premium_economy": "PREMIUM_ECONOMY",
    "business": "BUSINESS",
    "first": "FIRST",
}

# Common city → IATA mappings used to auto-resolve airport codes
_CITY_TO_IATA: dict[str, str] = {
    "seattle": "SEA", "new york": "JFK", "los angeles": "LAX",
    "san francisco": "SFO", "chicago": "ORD", "tokyo": "TYO",
    "london": "LON", "paris": "PAR", "dubai": "DXB",
    "singapore": "SIN", "sydney": "SYD", "toronto": "YYZ",
    "frankfurt": "FRA", "hong kong": "HKG", "bangkok": "BKK",
    "seoul": "ICN", "mumbai": "BOM", "rome": "FCO",
    "amsterdam": "AMS", "denver": "DEN", "miami": "MIA",
    "dallas": "DFW", "atlanta": "ATL", "boston": "BOS",
    "honolulu": "HNL",
}


def _resolve_iata(city_or_code: str) -> str:
    """Return an IATA code for *city_or_code* (best-effort)."""
    if len(city_or_code) == 3 and city_or_code.isalpha():
        return city_or_code.upper()
    return _CITY_TO_IATA.get(city_or_code.lower(), city_or_code[:3].upper())


def _parse_iso_duration(iso: str) -> str:
    """Convert ISO-8601 duration ``PT13H45M`` → ``13h 45m``."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", iso)
    if not m:
        return iso
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    return f"{hours}h {minutes}m"


class AmadeusFlightSource(BaseFlightSource):
    """Fetches cash flight prices from the Amadeus API."""

    info = SourceInfo(
        name="amadeus",
        domain="flights",
        fetch_method=FetchMethod.API,
        price_types=frozenset({PriceType.CASH}),
        priority=10,
        airlines=frozenset(),  # All airlines via GDS
    )

    def __init__(self, config: AmadeusConfig) -> None:
        self._config = config
        self._auth: AmadeusTokenManager | None = None

    async def is_available(self) -> bool:
        return self._config.is_configured

    async def close(self) -> None:
        if self._auth is not None:
            await self._auth.close()

    def _ensure_auth(self) -> AmadeusTokenManager:
        if self._auth is None:
            self._auth = AmadeusTokenManager(self._config)
        return self._auth

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
        auth = self._ensure_auth()
        client = await auth.get_client()

        params: dict[str, Any] = {
            "originLocationCode": _resolve_iata(origin),
            "destinationLocationCode": _resolve_iata(destination),
            "departureDate": departure_date,
            "adults": passengers,
            "travelClass": _CABIN_MAP.get(cabin_class, "ECONOMY"),
            "max": 50,
            "currencyCode": "USD",
        }
        if return_date:
            params["returnDate"] = return_date
        if max_price is not None:
            params["maxPrice"] = int(max_price)

        try:
            resp = await client.get("/v2/shopping/flight-offers", params=params)
            resp.raise_for_status()
        except Exception:
            logger.exception("Amadeus flight search failed")
            return []

        data: dict[str, Any] = resp.json()
        offers: list[dict[str, Any]] = data.get("data", [])
        carrier_dict: dict[str, str] = (
            data.get("dictionaries", {}).get("carriers", {})
        )

        results: list[dict[str, Any]] = []
        for offer in offers:
            try:
                result = self._normalise(
                    offer, carrier_dict, origin, destination,
                    cabin_class, passengers,
                )
                if result is not None:
                    if max_stops is not None and result["stops"] > max_stops:
                        continue
                    results.append(result)
            except Exception:
                logger.debug("Skipping unparseable offer", exc_info=True)

        results.sort(key=lambda r: r.get("price_usd") or float("inf"))
        return results

    # ----- helpers -----

    @staticmethod
    def _normalise(
        offer: dict[str, Any],
        carriers: dict[str, str],
        origin: str,
        destination: str,
        cabin_class: str,
        passengers: int,
    ) -> dict[str, Any] | None:
        itineraries = offer.get("itineraries", [])
        if not itineraries:
            return None
        itin = itineraries[0]
        segments = itin.get("segments", [])
        if not segments:
            return None

        first_seg = segments[0]
        last_seg = segments[-1]
        carrier_code = first_seg.get("carrierCode", "")
        airline = carriers.get(carrier_code, carrier_code)
        flight_num = f"{carrier_code}{first_seg.get('number', '')}"

        dep_time_raw = first_seg.get("departure", {}).get("at", "")
        dep_time = dep_time_raw[11:16] if len(dep_time_raw) > 15 else dep_time_raw
        dep_date = dep_time_raw[:10] if len(dep_time_raw) >= 10 else ""
        dep_airport = first_seg.get("departure", {}).get("iataCode", "")
        arr_airport = last_seg.get("arrival", {}).get("iataCode", "")

        duration = _parse_iso_duration(itin.get("duration", ""))
        stops = max(0, len(segments) - 1)

        price_total = float(offer.get("price", {}).get("grandTotal", 0))
        price_per = round(price_total / max(1, passengers), 2)

        seats_left: int | None = None
        if offer.get("numberOfBookableSeats"):
            seats_left = int(offer["numberOfBookableSeats"])

        return {
            "source": "amadeus",
            "flight_number": flight_num,
            "airline": airline,
            "origin": origin,
            "origin_airport": dep_airport,
            "destination": destination,
            "destination_airport": arr_airport,
            "date": dep_date,
            "departure_time": dep_time,
            "duration": duration,
            "stops": stops,
            "cabin_class": cabin_class,
            "price_usd": price_per,
            "total_price_usd": price_total,
            "passengers": passengers,
            "seats_remaining": seats_left,
        }
