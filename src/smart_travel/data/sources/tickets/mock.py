"""Mock ticket source — wraps the existing mock data layer."""

from __future__ import annotations

from typing import Any

from smart_travel.data.mock_tickets import search_tickets as _mock_search
from smart_travel.data.sources.base import (
    BaseTicketSource,
    FetchMethod,
    PriceType,
    SourceInfo,
)


class MockTicketSource(BaseTicketSource):
    """Wraps the existing mock ticket generator as a pluggable source."""

    info = SourceInfo(
        name="mock",
        domain="tickets",
        fetch_method=FetchMethod.MOCK,
        price_types=frozenset({PriceType.CASH}),
        priority=999,
    )

    async def is_available(self) -> bool:
        return True

    async def close(self) -> None:
        pass

    async def search_tickets(
        self,
        city: str,
        date_from: str,
        date_to: str,
        event_type: str | None = None,
        max_price: float | None = None,
        min_rating: float | None = None,
    ) -> list[dict[str, Any]]:
        results = _mock_search(
            city=city,
            date_from=date_from,
            date_to=date_to,
            event_type=event_type,
            max_price=max_price,
            min_rating=min_rating,
        )
        for r in results:
            r.setdefault("source", "mock")
        return results
