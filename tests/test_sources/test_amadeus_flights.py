"""Tests for the Amadeus flight source."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from smart_travel.config import AmadeusConfig
from smart_travel.data.sources.flights.amadeus import AmadeusFlightSource


@pytest.fixture
def config() -> AmadeusConfig:
    return AmadeusConfig(api_key="test_key", api_secret="test_secret", environment="test")


@pytest.fixture
def source(config: AmadeusConfig) -> AmadeusFlightSource:
    return AmadeusFlightSource(config)


# Sample Amadeus responses
TOKEN_RESPONSE = {
    "access_token": "test_token_123",
    "token_type": "Bearer",
    "expires_in": 1799,
}

FLIGHT_OFFERS_RESPONSE = {
    "data": [
        {
            "id": "1",
            "numberOfBookableSeats": 9,
            "itineraries": [
                {
                    "duration": "PT13H45M",
                    "segments": [
                        {
                            "departure": {
                                "iataCode": "SEA",
                                "at": "2026-05-01T14:30:00",
                            },
                            "arrival": {
                                "iataCode": "NRT",
                                "at": "2026-05-02T17:15:00",
                            },
                            "carrierCode": "UA",
                            "number": "876",
                        }
                    ],
                }
            ],
            "price": {
                "currency": "USD",
                "grandTotal": "650.50",
            },
        },
        {
            "id": "2",
            "numberOfBookableSeats": 3,
            "itineraries": [
                {
                    "duration": "PT16H20M",
                    "segments": [
                        {
                            "departure": {
                                "iataCode": "SEA",
                                "at": "2026-05-01T08:00:00",
                            },
                            "arrival": {
                                "iataCode": "LAX",
                                "at": "2026-05-01T10:30:00",
                            },
                            "carrierCode": "DL",
                            "number": "234",
                        },
                        {
                            "departure": {
                                "iataCode": "LAX",
                                "at": "2026-05-01T12:00:00",
                            },
                            "arrival": {
                                "iataCode": "NRT",
                                "at": "2026-05-02T16:20:00",
                            },
                            "carrierCode": "DL",
                            "number": "7",
                        },
                    ],
                }
            ],
            "price": {
                "currency": "USD",
                "grandTotal": "520.00",
            },
        },
    ],
    "dictionaries": {
        "carriers": {"UA": "United Airlines", "DL": "Delta Air Lines"},
    },
}


class TestAmadeusFlightSource:

    @pytest.mark.anyio
    async def test_is_available_with_keys(self, source: AmadeusFlightSource):
        assert await source.is_available()

    @pytest.mark.anyio
    async def test_is_unavailable_without_keys(self):
        src = AmadeusFlightSource(AmadeusConfig())
        assert not await src.is_available()

    @pytest.mark.anyio
    @respx.mock
    async def test_search_returns_normalised_results(self, source: AmadeusFlightSource):
        respx.post("https://test.api.amadeus.com/v1/security/oauth2/token").mock(
            return_value=httpx.Response(200, json=TOKEN_RESPONSE),
        )
        respx.get("https://test.api.amadeus.com/v2/shopping/flight-offers").mock(
            return_value=httpx.Response(200, json=FLIGHT_OFFERS_RESPONSE),
        )

        results = await source.search_flights("Seattle", "Tokyo", "2026-05-01")
        await source.close()

        assert len(results) == 2
        # Sorted by price
        assert results[0]["price_usd"] <= results[1]["price_usd"]

        # Check normalised fields
        first = results[0]
        assert first["source"] == "amadeus"
        assert first["origin"] == "Seattle"
        assert first["destination"] == "Tokyo"
        assert first["origin_airport"] in ("SEA", "LAX")
        assert "cabin_class" in first
        assert "duration" in first

    @pytest.mark.anyio
    @respx.mock
    async def test_token_refresh(self, source: AmadeusFlightSource):
        token_route = respx.post(
            "https://test.api.amadeus.com/v1/security/oauth2/token"
        ).mock(return_value=httpx.Response(200, json=TOKEN_RESPONSE))

        respx.get("https://test.api.amadeus.com/v2/shopping/flight-offers").mock(
            return_value=httpx.Response(200, json=FLIGHT_OFFERS_RESPONSE),
        )

        await source.search_flights("Seattle", "Tokyo", "2026-05-01")
        assert token_route.call_count == 1
        await source.close()

    @pytest.mark.anyio
    @respx.mock
    async def test_stops_count(self, source: AmadeusFlightSource):
        respx.post("https://test.api.amadeus.com/v1/security/oauth2/token").mock(
            return_value=httpx.Response(200, json=TOKEN_RESPONSE),
        )
        respx.get("https://test.api.amadeus.com/v2/shopping/flight-offers").mock(
            return_value=httpx.Response(200, json=FLIGHT_OFFERS_RESPONSE),
        )

        results = await source.search_flights("Seattle", "Tokyo", "2026-05-01")
        await source.close()

        # First offer: 1 segment → 0 stops
        non_stop = [r for r in results if r["flight_number"] == "UA876"]
        assert len(non_stop) == 1
        assert non_stop[0]["stops"] == 0

        # Second offer: 2 segments → 1 stop
        one_stop = [r for r in results if r["flight_number"] == "DL234"]
        assert len(one_stop) == 1
        assert one_stop[0]["stops"] == 1

    @pytest.mark.anyio
    @respx.mock
    async def test_api_error_returns_empty(self, source: AmadeusFlightSource):
        respx.post("https://test.api.amadeus.com/v1/security/oauth2/token").mock(
            return_value=httpx.Response(200, json=TOKEN_RESPONSE),
        )
        respx.get("https://test.api.amadeus.com/v2/shopping/flight-offers").mock(
            return_value=httpx.Response(500, text="Internal Server Error"),
        )

        results = await source.search_flights("Seattle", "Tokyo", "2026-05-01")
        await source.close()
        assert results == []

    @pytest.mark.anyio
    @respx.mock
    async def test_max_stops_filter(self, source: AmadeusFlightSource):
        respx.post("https://test.api.amadeus.com/v1/security/oauth2/token").mock(
            return_value=httpx.Response(200, json=TOKEN_RESPONSE),
        )
        respx.get("https://test.api.amadeus.com/v2/shopping/flight-offers").mock(
            return_value=httpx.Response(200, json=FLIGHT_OFFERS_RESPONSE),
        )

        results = await source.search_flights(
            "Seattle", "Tokyo", "2026-05-01", max_stops=0,
        )
        await source.close()
        # Should exclude the 1-stop flight
        assert all(r["stops"] == 0 for r in results)
