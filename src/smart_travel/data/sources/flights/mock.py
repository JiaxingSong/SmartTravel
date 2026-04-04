"""Mock flight source — wraps the existing mock data layer.

Always available, always returns data.  Used as the last-resort fallback
when no live API sources are configured.
"""

from __future__ import annotations

from typing import Any

from smart_travel.data.mock_flights import search_flights as _mock_search
from smart_travel.data.sources.base import (
    BaseFlightSource,
    FetchMethod,
    PriceType,
    SourceInfo,
)


class MockFlightSource(BaseFlightSource):
    """Wraps the existing mock flight generator as a pluggable source."""

    info = SourceInfo(
        name="mock",
        domain="flights",
        fetch_method=FetchMethod.MOCK,
        price_types=frozenset({PriceType.CASH, PriceType.POINTS}),
        priority=999,
        airlines=frozenset(),
    )

    async def is_available(self) -> bool:
        return True

    async def close(self) -> None:
        pass

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
        results = _mock_search(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            cabin_class=cabin_class,
            passengers=passengers,
            max_price=max_price,
            max_stops=max_stops,
        )
        # Tag each result with its source
        for r in results:
            r.setdefault("source", "mock")
            # For round-trip results, also tag inner lists
            if isinstance(r.get("outbound"), list):
                for f in r["outbound"]:
                    f.setdefault("source", "mock")
            if isinstance(r.get("return"), list):
                for f in r["return"]:
                    f.setdefault("source", "mock")
        return results
