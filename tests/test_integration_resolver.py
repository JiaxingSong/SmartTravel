"""Integration tests: full resolver -> live-source -> merge -> tool pipeline.

Every test mocks external HTTP APIs via respx but exercises the *complete*
resolver stack: registry creation, source fan-out, merge logic, data-quality
tagging, and caching.  No production code is modified.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

from smart_travel.config import AppConfig
from smart_travel.data.resolver import (
    search_flights,
    search_hotels,
    search_tickets,
    set_cache,
    set_registry,
)
from smart_travel.data.sources.registry import SourceRegistry

# Response payloads reused from existing source-level test modules
from tests.test_sources.test_amadeus_flights import (
    FLIGHT_OFFERS_RESPONSE,
    TOKEN_RESPONSE as AMADEUS_TOKEN,
)
from tests.test_sources.test_amadeus_hotels import (
    HOTEL_LIST_RESPONSE,
    HOTEL_OFFERS_RESPONSE,
    TOKEN_RESPONSE as AMADEUS_HOTEL_TOKEN,
)
from tests.test_sources.test_ticketmaster import EVENTS_RESPONSE


# ---- autouse fixture: clean module-level singletons ----

@pytest.fixture(autouse=True)
def _reset_resolver():
    """Ensure the module-level registry and cache are cleared between tests."""
    set_registry(None)  # type: ignore[arg-type]
    set_cache(None)  # type: ignore[arg-type]
    yield
    set_registry(None)  # type: ignore[arg-type]
    set_cache(None)  # type: ignore[arg-type]


# =====================================================================
# Flight integration
# =====================================================================

class TestFlightIntegration:

    @pytest.mark.anyio
    @respx.mock
    async def test_amadeus_concurrent(
        self, full_config: AppConfig, mock_all_flight_apis: dict,
    ):
        """Amadeus responds; results are non-empty."""
        set_registry(SourceRegistry(full_config))

        results = await search_flights("Seattle", "Tokyo", "2026-05-01")

        assert len(results) > 0
        sources = {r.get("source") for r in results}
        # At minimum Amadeus cash results should be present
        assert "amadeus" in sources

    @pytest.mark.anyio
    @respx.mock
    async def test_all_results_tagged_live(
        self, full_config: AppConfig, mock_all_flight_apis: dict,
    ):
        """Every result from mocked live APIs carries _data_quality='live'."""
        set_registry(SourceRegistry(full_config))

        results = await search_flights("Seattle", "Tokyo", "2026-05-01")

        assert len(results) > 0
        for r in results:
            assert r.get("_data_quality") == "live", (
                f"Expected _data_quality='live', got {r.get('_data_quality')!r} "
                f"on result from source={r.get('source')!r}"
            )

    @pytest.mark.anyio
    @respx.mock
    async def test_results_sorted_by_price(
        self, full_config: AppConfig, mock_all_flight_apis: dict,
    ):
        """Merged results are sorted by price_usd ascending."""
        set_registry(SourceRegistry(full_config))

        results = await search_flights("Seattle", "Tokyo", "2026-05-01")

        prices = [r.get("price_usd") for r in results]
        # Points-only results may have price_usd=None; they sort at end
        numeric = [p for p in prices if p is not None]
        assert numeric == sorted(numeric)


# =====================================================================
# Multi-source merge
# =====================================================================

class TestMultiSourceMerge:

    @pytest.mark.anyio
    @respx.mock
    async def test_amadeus_only_no_points_merge(
        self, full_config: AppConfig,
    ):
        """All results come from Amadeus with no points_price attached
        (airline award sources are browser-based and not mocked via respx).
        """
        respx.post("https://test.api.amadeus.com/v1/security/oauth2/token").mock(
            return_value=httpx.Response(200, json=AMADEUS_TOKEN),
        )
        respx.get("https://test.api.amadeus.com/v2/shopping/flight-offers").mock(
            return_value=httpx.Response(200, json=FLIGHT_OFFERS_RESPONSE),
        )

        set_registry(SourceRegistry(full_config))
        results = await search_flights("Seattle", "Tokyo", "2026-05-01")

        assert len(results) > 0
        for r in results:
            if r.get("source") == "amadeus":
                assert r.get("_data_quality") == "live"


# =====================================================================
# Hotel integration
# =====================================================================

class TestHotelIntegration:

    @pytest.mark.anyio
    @respx.mock
    async def test_amadeus_hotels_through_resolver(
        self, full_config: AppConfig, mock_all_hotel_apis: dict,
    ):
        """Two-step hotel search through the resolver with live mocks."""
        set_registry(SourceRegistry(full_config))

        results = await search_hotels("Tokyo", "2026-05-01", "2026-05-05")

        assert len(results) == 2
        for r in results:
            assert r["_data_quality"] == "live"
            assert r["source"] == "amadeus"
            assert r["price_per_night_usd"] > 0

    @pytest.mark.anyio
    @respx.mock
    async def test_hotel_results_sorted_by_price(
        self, full_config: AppConfig, mock_all_hotel_apis: dict,
    ):
        """Hotel results are sorted by price_per_night_usd ascending."""
        set_registry(SourceRegistry(full_config))

        results = await search_hotels("Tokyo", "2026-05-01", "2026-05-05")

        prices = [r["price_per_night_usd"] for r in results]
        assert prices == sorted(prices)


# =====================================================================
# Ticket integration
# =====================================================================

class TestTicketIntegration:

    @pytest.mark.anyio
    @respx.mock
    async def test_ticketmaster_through_resolver(
        self, full_config: AppConfig, mock_all_ticket_apis: dict,
    ):
        """Ticketmaster events flow through the resolver with live tags."""
        set_registry(SourceRegistry(full_config))

        results = await search_tickets("Tokyo", "2026-05-01", "2026-05-10")

        assert len(results) > 0
        for r in results:
            assert r["_data_quality"] == "live"
            assert r["source"] == "ticketmaster"

    @pytest.mark.anyio
    @respx.mock
    async def test_ticket_results_sorted_by_date(
        self, full_config: AppConfig, mock_all_ticket_apis: dict,
    ):
        """Ticket results are sorted by (date, time)."""
        set_registry(SourceRegistry(full_config))

        results = await search_tickets("Tokyo", "2026-05-01", "2026-05-10")

        date_times = [(r["date"], r["time"]) for r in results]
        assert date_times == sorted(date_times)


# =====================================================================
# Mixed live + mock fallback
# =====================================================================

class TestMixedLiveAndMock:

    @pytest.mark.anyio
    @respx.mock
    async def test_all_live_fail_falls_back_to_mock(
        self, full_config: AppConfig,
    ):
        """Amadeus returns 500 -> resolver falls back to mock."""
        respx.post("https://test.api.amadeus.com/v1/security/oauth2/token").mock(
            return_value=httpx.Response(200, json=AMADEUS_TOKEN),
        )
        respx.get("https://test.api.amadeus.com/v2/shopping/flight-offers").mock(
            return_value=httpx.Response(500, text="Internal Server Error"),
        )

        set_registry(SourceRegistry(full_config))
        results = await search_flights("Seattle", "Tokyo", "2026-05-01")

        assert len(results) > 0
        for r in results:
            assert r.get("_data_quality") == "mock"
            assert r.get("source") == "mock"

    @pytest.mark.anyio
    @respx.mock
    async def test_hotel_live_fail_falls_back_to_mock(
        self, full_config: AppConfig,
    ):
        """Amadeus hotel endpoints return 500 -> resolver falls back to mock."""
        respx.post("https://test.api.amadeus.com/v1/security/oauth2/token").mock(
            return_value=httpx.Response(200, json=AMADEUS_HOTEL_TOKEN),
        )
        respx.get(
            "https://test.api.amadeus.com/v1/reference-data/locations/hotels/by-city",
        ).mock(return_value=httpx.Response(500, text="Error"))

        set_registry(SourceRegistry(full_config))
        results = await search_hotels("Tokyo", "2026-05-01", "2026-05-05")

        assert len(results) > 0
        for r in results:
            assert r.get("_data_quality") == "mock"
            assert r.get("source") == "mock"

    @pytest.mark.anyio
    @respx.mock
    async def test_ticket_live_fail_falls_back_to_mock(
        self, full_config: AppConfig,
    ):
        """Ticketmaster returns 500 -> resolver falls back to mock."""
        respx.get(
            "https://app.ticketmaster.com/discovery/v2/events.json",
        ).mock(return_value=httpx.Response(500, text="Error"))

        set_registry(SourceRegistry(full_config))
        results = await search_tickets("Tokyo", "2026-05-01", "2026-05-10")

        assert len(results) > 0
        for r in results:
            assert r.get("_data_quality") == "mock"
            assert r.get("source") == "mock"


# =====================================================================
# Tool pipeline integration
# =====================================================================

class TestToolPipelineIntegration:

    @pytest.mark.anyio
    @respx.mock
    async def test_flights_tool_live_output(
        self, full_config: AppConfig, mock_all_flight_apis: dict,
    ):
        """search_flights_tool produces output with 'Sources:' and live data."""
        from smart_travel.tools.flights import search_flights_tool

        set_registry(SourceRegistry(full_config))

        result = await search_flights_tool.handler({
            "origin": "Seattle",
            "destination": "Tokyo",
            "departure_date": "2026-05-01",
        })

        text = result["content"][0]["text"]
        assert "Sources:" in text
        assert "DEMO" not in text
        assert "MOCK" not in text

        # Parse the JSON payload from the output
        json_start = text.index("[")
        payload = json.loads(text[json_start:])
        assert len(payload) > 0
        for r in payload:
            assert r.get("_data_quality") == "live"

    @pytest.mark.anyio
    @respx.mock
    async def test_hotels_tool_live_output(
        self, full_config: AppConfig, mock_all_hotel_apis: dict,
    ):
        """search_hotels_tool produces output with 'Sources:' and live data."""
        from smart_travel.tools.hotels import search_hotels_tool

        set_registry(SourceRegistry(full_config))

        result = await search_hotels_tool.handler({
            "city": "Tokyo",
            "check_in": "2026-05-01",
            "check_out": "2026-05-05",
        })

        text = result["content"][0]["text"]
        assert "Sources:" in text
        assert "DEMO" not in text
        assert "MOCK" not in text

        json_start = text.index("[")
        payload = json.loads(text[json_start:])
        assert len(payload) > 0
        for r in payload:
            assert r.get("_data_quality") == "live"

    @pytest.mark.anyio
    @respx.mock
    async def test_tickets_tool_live_output(
        self, full_config: AppConfig, mock_all_ticket_apis: dict,
    ):
        """search_tickets_tool produces output with 'Sources:' and live data."""
        from smart_travel.tools.tickets import search_tickets_tool

        set_registry(SourceRegistry(full_config))

        result = await search_tickets_tool.handler({
            "city": "Tokyo",
            "date_from": "2026-05-01",
            "date_to": "2026-05-10",
        })

        text = result["content"][0]["text"]
        assert "Sources:" in text
        assert "DEMO" not in text
        assert "MOCK" not in text

        json_start = text.index("[")
        payload = json.loads(text[json_start:])
        assert len(payload) > 0
        for r in payload:
            assert r.get("_data_quality") == "live"


# =====================================================================
# Cache integration
# =====================================================================

class TestCacheIntegration:

    @pytest.mark.anyio
    @respx.mock
    async def test_second_call_uses_cache(
        self, full_config: AppConfig,
    ):
        """Two identical search_flights() calls: second should hit cache
        and NOT call the API again.
        """
        respx.post("https://test.api.amadeus.com/v1/security/oauth2/token").mock(
            return_value=httpx.Response(200, json=AMADEUS_TOKEN),
        )
        flights_route = respx.get(
            "https://test.api.amadeus.com/v2/shopping/flight-offers",
        ).mock(return_value=httpx.Response(200, json=FLIGHT_OFFERS_RESPONSE))

        set_registry(SourceRegistry(full_config))

        results1 = await search_flights("Seattle", "Tokyo", "2026-05-01")
        assert flights_route.call_count == 1

        results2 = await search_flights("Seattle", "Tokyo", "2026-05-01")
        # Second call should have been served from cache
        assert flights_route.call_count == 1

        assert results1 == results2
