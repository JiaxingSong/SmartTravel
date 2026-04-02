"""Amadeus Hotel Offers Search — cash prices via REST API.

Uses a two-step process:
1. ``/v1/reference-data/locations/hotels/by-city`` to get hotel IDs
2. ``/v3/shopping/hotel-offers`` to get prices for those hotels
"""

from __future__ import annotations

import logging
from typing import Any

from smart_travel.config import AmadeusConfig
from smart_travel.data.sources._amadeus_auth import AmadeusTokenManager
from smart_travel.data.sources.base import (
    BaseHotelSource,
    FetchMethod,
    PriceType,
    SourceInfo,
)

logger = logging.getLogger(__name__)

_CITY_TO_IATA: dict[str, str] = {
    "seattle": "SEA", "new york": "NYC", "los angeles": "LAX",
    "san francisco": "SFO", "chicago": "CHI", "tokyo": "TYO",
    "london": "LON", "paris": "PAR", "dubai": "DXB",
    "singapore": "SIN", "sydney": "SYD", "toronto": "YTO",
    "frankfurt": "FRA", "hong kong": "HKG", "bangkok": "BKK",
    "seoul": "SEL", "mumbai": "BOM", "rome": "ROM",
    "amsterdam": "AMS", "denver": "DEN", "miami": "MIA",
    "dallas": "DFW", "atlanta": "ATL", "boston": "BOS",
    "honolulu": "HNL",
}


def _resolve_city_code(city: str) -> str:
    if len(city) == 3 and city.isalpha():
        return city.upper()
    return _CITY_TO_IATA.get(city.lower(), city[:3].upper())


class AmadeusHotelSource(BaseHotelSource):
    """Fetches cash hotel prices from the Amadeus API."""

    info = SourceInfo(
        name="amadeus",
        domain="hotels",
        fetch_method=FetchMethod.API,
        price_types=frozenset({PriceType.CASH}),
        priority=10,
        hotel_chains=frozenset(),  # All chains
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

    # ----- public search -----

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
        auth = self._ensure_auth()
        client = await auth.get_client()

        city_code = _resolve_city_code(city)

        # Step 1 — get hotel IDs by city
        hotel_ids = await self._get_hotel_ids(client, city_code, min_stars)
        if not hotel_ids:
            return []

        # Step 2 — get offers for those hotels
        offers = await self._get_offers(
            client, hotel_ids, check_in, check_out, guests, rooms,
        )

        # Normalise
        from datetime import datetime
        try:
            nights = max(1, (datetime.strptime(check_out, "%Y-%m-%d")
                             - datetime.strptime(check_in, "%Y-%m-%d")).days)
        except (ValueError, TypeError):
            nights = 1

        results: list[dict[str, Any]] = []
        for offer_data in offers:
            try:
                r = self._normalise(
                    offer_data, city, check_in, check_out,
                    guests, rooms, nights,
                )
                if r is not None:
                    if (max_price_per_night is not None
                            and r["price_per_night_usd"] > max_price_per_night):
                        continue
                    results.append(r)
            except Exception:
                logger.debug("Skipping unparseable hotel offer", exc_info=True)

        results.sort(key=lambda r: r["price_per_night_usd"])
        return results

    # ----- helpers -----

    async def _get_hotel_ids(
        self,
        client: Any,
        city_code: str,
        min_stars: int | None,
    ) -> list[str]:
        params: dict[str, Any] = {
            "cityCode": city_code,
            "radius": 30,
            "radiusUnit": "KM",
        }
        if min_stars is not None:
            params["ratings"] = ",".join(str(s) for s in range(min_stars, 6))

        try:
            resp = await client.get(
                "/v1/reference-data/locations/hotels/by-city",
                params=params,
            )
            resp.raise_for_status()
        except Exception:
            logger.exception("Amadeus hotel list failed")
            return []

        data = resp.json().get("data", [])
        return [h["hotelId"] for h in data[:20]]  # limit for offer query

    async def _get_offers(
        self,
        client: Any,
        hotel_ids: list[str],
        check_in: str,
        check_out: str,
        guests: int,
        rooms: int,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "hotelIds": ",".join(hotel_ids),
            "checkInDate": check_in,
            "checkOutDate": check_out,
            "adults": guests,
            "roomQuantity": rooms,
            "currency": "USD",
        }

        try:
            resp = await client.get(
                "/v3/shopping/hotel-offers",
                params=params,
            )
            resp.raise_for_status()
        except Exception:
            logger.exception("Amadeus hotel offers failed")
            return []

        return resp.json().get("data", [])

    @staticmethod
    def _normalise(
        offer_data: dict[str, Any],
        city: str,
        check_in: str,
        check_out: str,
        guests: int,
        rooms: int,
        nights: int,
    ) -> dict[str, Any] | None:
        hotel = offer_data.get("hotel", {})
        name = hotel.get("name", "Unknown Hotel")
        star_raw = hotel.get("rating")
        star_rating = int(star_raw) if star_raw else None

        offers = offer_data.get("offers", [])
        if not offers:
            return None
        first_offer = offers[0]

        price_info = first_offer.get("price", {})
        total_str = price_info.get("total", "0")
        total_price = float(total_str)
        per_night = round(total_price / max(1, nights * rooms), 2)

        # Cancellation
        policies = first_offer.get("policies", {})
        cancel_info = policies.get("cancellations", [{}])
        cancel_policy = "Non-refundable"
        if cancel_info and cancel_info[0].get("type") == "FULL_REFUNDABLE":
            deadline = cancel_info[0].get("deadline", "")
            cancel_policy = f"Free cancellation until {deadline}" if deadline else "Free cancellation"

        return {
            "source": "amadeus",
            "name": name,
            "city": city,
            "neighborhood": "",
            "star_rating": star_rating,
            "guest_rating": None,
            "review_count": None,
            "price_per_night_usd": per_night,
            "total_price_usd": total_price,
            "total_nights": nights,
            "check_in": check_in,
            "check_out": check_out,
            "guests": guests,
            "rooms": rooms,
            "amenities": [],
            "cancellation_policy": cancel_policy,
            "rooms_available": None,
        }
