"""Tests for the seats.aero flight source."""

from __future__ import annotations

import httpx
import pytest
import respx

from smart_travel.config import SeatsAeroConfig
from smart_travel.data.sources.flights.seats_aero import SeatsAeroFlightSource


@pytest.fixture
def config() -> SeatsAeroConfig:
    return SeatsAeroConfig(api_key="test_partner_key")


@pytest.fixture
def source(config: SeatsAeroConfig) -> SeatsAeroFlightSource:
    return SeatsAeroFlightSource(config)


SEARCH_RESPONSE = {
    "data": [
        {
            "Route": "SEA-NRT",
            "Date": "2026-05-01",
            "Source": "united",
            "Airlines": "UA",
            "YMileageCost": 70000,
            "YDirect": True,
            "YRemainingSeats": 4,
            "JMileageCost": 120000,
            "JDirect": True,
            "JRemainingSeats": 2,
            "FMileageCost": 0,
            "FDirect": False,
            "FRemainingSeats": 0,
        },
        {
            "Route": "SEA-NRT",
            "Date": "2026-05-01",
            "Source": "aeroplan",
            "Airlines": "AC,NH",
            "YMileageCost": 55000,
            "YDirect": False,
            "YRemainingSeats": 9,
            "JMileageCost": 0,
            "JDirect": False,
            "JRemainingSeats": 0,
            "FMileageCost": 0,
            "FDirect": False,
            "FRemainingSeats": 0,
        },
    ]
}


class TestSeatsAeroFlightSource:

    @pytest.mark.anyio
    async def test_is_available_with_key(self, source: SeatsAeroFlightSource):
        assert await source.is_available()

    @pytest.mark.anyio
    async def test_is_unavailable_without_key(self):
        src = SeatsAeroFlightSource(SeatsAeroConfig())
        assert not await src.is_available()

    @pytest.mark.anyio
    @respx.mock
    async def test_search_economy(self, source: SeatsAeroFlightSource):
        respx.get("https://seats.aero/partnerapi/search").mock(
            return_value=httpx.Response(200, json=SEARCH_RESPONSE),
        )

        results = await source.search_flights(
            "Seattle", "Tokyo", "2026-05-01", cabin_class="economy",
        )
        await source.close()

        assert len(results) == 2
        # Sorted by points price
        assert results[0]["points_price"] <= results[1]["points_price"]

        # Check fields
        first = results[0]
        assert first["source"] == "seats_aero"
        assert first["points_price"] == 55000
        assert first["points_program"] == "aeroplan"

    @pytest.mark.anyio
    @respx.mock
    async def test_search_business(self, source: SeatsAeroFlightSource):
        respx.get("https://seats.aero/partnerapi/search").mock(
            return_value=httpx.Response(200, json=SEARCH_RESPONSE),
        )

        results = await source.search_flights(
            "Seattle", "Tokyo", "2026-05-01", cabin_class="business",
        )
        await source.close()

        # Only United has JMileageCost > 0
        assert len(results) == 1
        assert results[0]["points_price"] == 120000

    @pytest.mark.anyio
    @respx.mock
    async def test_auth_header(self, source: SeatsAeroFlightSource):
        route = respx.get("https://seats.aero/partnerapi/search").mock(
            return_value=httpx.Response(200, json=SEARCH_RESPONSE),
        )

        await source.search_flights("Seattle", "Tokyo", "2026-05-01")
        await source.close()

        assert route.call_count == 1
        req = route.calls[0].request
        assert req.headers["Partner-Authorization"] == "test_partner_key"

    @pytest.mark.anyio
    @respx.mock
    async def test_api_error_returns_empty(self, source: SeatsAeroFlightSource):
        respx.get("https://seats.aero/partnerapi/search").mock(
            return_value=httpx.Response(500, text="Error"),
        )

        results = await source.search_flights("Seattle", "Tokyo", "2026-05-01")
        await source.close()
        assert results == []
