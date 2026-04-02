"""Tests for the Ticketmaster source."""

from __future__ import annotations

import httpx
import pytest
import respx

from smart_travel.config import TicketmasterConfig
from smart_travel.data.sources.tickets.ticketmaster import TicketmasterSource


@pytest.fixture
def config() -> TicketmasterConfig:
    return TicketmasterConfig(api_key="test_tm_key")


@pytest.fixture
def source(config: TicketmasterConfig) -> TicketmasterSource:
    return TicketmasterSource(config)


EVENTS_RESPONSE = {
    "_embedded": {
        "events": [
            {
                "name": "Coldplay World Tour",
                "dates": {
                    "start": {
                        "localDate": "2026-05-05",
                        "localTime": "19:30:00",
                    }
                },
                "_embedded": {
                    "venues": [{"name": "Tokyo Dome"}],
                },
                "classifications": [
                    {"segment": {"name": "Music"}},
                ],
                "priceRanges": [
                    {"min": 75.0, "max": 350.0, "currency": "USD"},
                ],
                "url": "https://ticketmaster.com/event/12345",
            },
            {
                "name": "NBA Basketball",
                "dates": {
                    "start": {
                        "localDate": "2026-05-07",
                        "localTime": "20:00:00",
                    }
                },
                "_embedded": {
                    "venues": [{"name": "Tokyo Arena"}],
                },
                "classifications": [
                    {"segment": {"name": "Sports"}},
                ],
                "priceRanges": [
                    {"min": 40.0, "max": 200.0, "currency": "USD"},
                ],
                "url": "https://ticketmaster.com/event/67890",
            },
        ]
    }
}


class TestTicketmasterSource:

    @pytest.mark.anyio
    async def test_is_available_with_key(self, source: TicketmasterSource):
        assert await source.is_available()

    @pytest.mark.anyio
    async def test_is_unavailable_without_key(self):
        src = TicketmasterSource(TicketmasterConfig())
        assert not await src.is_available()

    @pytest.mark.anyio
    @respx.mock
    async def test_search_returns_normalised(self, source: TicketmasterSource):
        respx.get("https://app.ticketmaster.com/discovery/v2/events.json").mock(
            return_value=httpx.Response(200, json=EVENTS_RESPONSE),
        )

        results = await source.search_tickets("Tokyo", "2026-05-01", "2026-05-10")
        await source.close()

        assert len(results) == 2
        first = results[0]
        assert first["source"] == "ticketmaster"
        assert first["city"] == "Tokyo"
        assert first["date"] == "2026-05-05"
        assert first["time"] == "19:30"
        assert first["venue"] == "Tokyo Dome"

    @pytest.mark.anyio
    @respx.mock
    async def test_event_type_classification(self, source: TicketmasterSource):
        respx.get("https://app.ticketmaster.com/discovery/v2/events.json").mock(
            return_value=httpx.Response(200, json=EVENTS_RESPONSE),
        )

        results = await source.search_tickets("Tokyo", "2026-05-01", "2026-05-10")
        await source.close()

        types = {r["event_type"] for r in results}
        assert "concert" in types
        assert "sports" in types

    @pytest.mark.anyio
    @respx.mock
    async def test_price_extraction(self, source: TicketmasterSource):
        respx.get("https://app.ticketmaster.com/discovery/v2/events.json").mock(
            return_value=httpx.Response(200, json=EVENTS_RESPONSE),
        )

        results = await source.search_tickets("Tokyo", "2026-05-01", "2026-05-10")
        await source.close()

        for r in results:
            assert r["price_range_usd"]["min"] <= r["price_range_usd"]["max"]
            avg = r["average_price_usd"]
            assert r["price_range_usd"]["min"] <= avg <= r["price_range_usd"]["max"]

    @pytest.mark.anyio
    @respx.mock
    async def test_max_price_filter(self, source: TicketmasterSource):
        respx.get("https://app.ticketmaster.com/discovery/v2/events.json").mock(
            return_value=httpx.Response(200, json=EVENTS_RESPONSE),
        )

        results = await source.search_tickets(
            "Tokyo", "2026-05-01", "2026-05-10", max_price=100.0,
        )
        await source.close()

        # NBA avg = (40+200)/2 = 120 → excluded
        # Coldplay avg = (75+350)/2 = 212.5 → excluded
        assert len(results) == 0

    @pytest.mark.anyio
    @respx.mock
    async def test_api_error_returns_empty(self, source: TicketmasterSource):
        respx.get("https://app.ticketmaster.com/discovery/v2/events.json").mock(
            return_value=httpx.Response(500, text="Error"),
        )

        results = await source.search_tickets("Tokyo", "2026-05-01", "2026-05-10")
        await source.close()
        assert results == []
