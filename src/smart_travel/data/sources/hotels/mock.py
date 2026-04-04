"""Mock hotel source — wraps the existing mock data layer."""

from __future__ import annotations

from typing import Any

from smart_travel.data.mock_hotels import search_hotels as _mock_search
from smart_travel.data.sources.base import (
    BaseHotelSource,
    FetchMethod,
    PriceType,
    SourceInfo,
)


class MockHotelSource(BaseHotelSource):
    """Wraps the existing mock hotel generator as a pluggable source."""

    info = SourceInfo(
        name="mock",
        domain="hotels",
        fetch_method=FetchMethod.MOCK,
        price_types=frozenset({PriceType.CASH, PriceType.POINTS}),
        priority=999,
        hotel_chains=frozenset(),
    )

    async def is_available(self) -> bool:
        return True

    async def close(self) -> None:
        pass

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
        results = _mock_search(
            city=city,
            check_in=check_in,
            check_out=check_out,
            guests=guests,
            rooms=rooms,
            min_stars=min_stars,
            max_price_per_night=max_price_per_night,
            required_amenities=required_amenities,
        )
        for r in results:
            r.setdefault("source", "mock")
        return results
