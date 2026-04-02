"""seats.aero — award / points flight availability.

Uses the seats.aero Partner API to retrieve mileage program award
availability (e.g. United MileagePlus, Aeroplan, etc.).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from smart_travel.config import SeatsAeroConfig
from smart_travel.data.sources.base import (
    BaseFlightSource,
    FetchMethod,
    PriceType,
    SourceInfo,
)

logger = logging.getLogger(__name__)

# seats.aero uses its own location meta-codes for metro areas
_CITY_TO_SEATS_CODE: dict[str, str] = {
    "new york": "NYC", "tokyo": "TYO", "london": "LON",
    "paris": "PAR", "chicago": "CHI", "los angeles": "LAX",
    "san francisco": "SFO", "seattle": "SEA", "miami": "MIA",
    "toronto": "YTO", "seoul": "SEL", "singapore": "SIN",
    "sydney": "SYD", "dubai": "DXB", "hong kong": "HKG",
    "bangkok": "BKK", "mumbai": "BOM", "delhi": "DEL",
    "amsterdam": "AMS", "frankfurt": "FRA", "rome": "ROM",
    "dallas": "DFW", "denver": "DEN", "atlanta": "ATL",
    "boston": "BOS", "honolulu": "HNL",
}

_CABIN_MAP: dict[str, str] = {
    "economy": "Y",
    "premium_economy": "W",
    "business": "J",
    "first": "F",
}


def _resolve_code(city_or_code: str) -> str:
    if len(city_or_code) == 3 and city_or_code.isalpha():
        return city_or_code.upper()
    return _CITY_TO_SEATS_CODE.get(city_or_code.lower(), city_or_code[:3].upper())


class SeatsAeroFlightSource(BaseFlightSource):
    """Fetches points/award availability from the seats.aero Partner API."""

    info = SourceInfo(
        name="seats_aero",
        domain="flights",
        fetch_method=FetchMethod.API,
        price_types=frozenset({PriceType.POINTS}),
        priority=10,
        airlines=frozenset(),  # All programs
    )

    def __init__(self, config: SeatsAeroConfig) -> None:
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
                headers={"Partner-Authorization": self._config.api_key},
            )
        return self._client

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
        client = self._ensure_client()

        origin_code = _resolve_code(origin)
        dest_code = _resolve_code(destination)

        params: dict[str, str] = {
            "origin": origin_code,
            "destination": dest_code,
            "date": departure_date,
        }

        try:
            resp = await client.get("/search", params=params)
            resp.raise_for_status()
        except Exception:
            logger.exception("seats.aero search failed")
            return []

        body: dict[str, Any] = resp.json()
        raw_results: list[dict[str, Any]] = body.get("data", [])

        cabin_key = _CABIN_MAP.get(cabin_class, "Y")
        results: list[dict[str, Any]] = []

        for entry in raw_results:
            try:
                result = self._normalise(
                    entry, cabin_key, origin, destination,
                    cabin_class, passengers,
                )
                if result is not None:
                    results.append(result)
            except Exception:
                logger.debug("Skipping unparseable seats.aero entry", exc_info=True)

        results.sort(key=lambda r: r.get("points_price") or float("inf"))
        return results

    @staticmethod
    def _normalise(
        entry: dict[str, Any],
        cabin_key: str,
        origin: str,
        destination: str,
        cabin_class: str,
        passengers: int,
    ) -> dict[str, Any] | None:
        # seats.aero returns {Y,W,J,F}MileageCost and {Y,W,J,F}Direct etc.
        mileage_field = f"{cabin_key}MileageCost"
        mileage = entry.get(mileage_field)
        if mileage is None or mileage == 0:
            return None

        source_name = entry.get("Source", entry.get("source", ""))
        route = entry.get("Route", "")
        parts = route.split("-") if route else ["", ""]
        dep_airport = parts[0] if len(parts) > 0 else ""
        arr_airport = parts[-1] if len(parts) > 1 else ""

        date = entry.get("Date", entry.get("date", ""))
        airlines_raw = entry.get("Airlines", entry.get("airlines", ""))

        # Direct flag
        direct_field = f"{cabin_key}Direct"
        is_direct = entry.get(direct_field, False)
        stops = 0 if is_direct else 1

        remaining_field = f"{cabin_key}RemainingSeats"
        seats = entry.get(remaining_field)

        return {
            "source": "seats_aero",
            "flight_number": "",
            "airline": airlines_raw,
            "origin": origin,
            "origin_airport": dep_airport,
            "destination": destination,
            "destination_airport": arr_airport,
            "date": date,
            "departure_time": "",
            "duration": "",
            "stops": stops,
            "cabin_class": cabin_class,
            "passengers": passengers,
            "points_price": int(mileage),
            "points_program": source_name.lower() if source_name else None,
            "seats_remaining": int(seats) if seats else None,
        }
