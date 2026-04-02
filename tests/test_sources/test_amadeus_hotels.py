"""Tests for the Amadeus hotel source."""

from __future__ import annotations

import httpx
import pytest
import respx

from smart_travel.config import AmadeusConfig
from smart_travel.data.sources.hotels.amadeus import AmadeusHotelSource


@pytest.fixture
def config() -> AmadeusConfig:
    return AmadeusConfig(api_key="test_key", api_secret="test_secret", environment="test")


@pytest.fixture
def source(config: AmadeusConfig) -> AmadeusHotelSource:
    return AmadeusHotelSource(config)


TOKEN_RESPONSE = {
    "access_token": "test_token_123",
    "token_type": "Bearer",
    "expires_in": 1799,
}

HOTEL_LIST_RESPONSE = {
    "data": [
        {"hotelId": "HTLX0001"},
        {"hotelId": "HTLX0002"},
    ]
}

HOTEL_OFFERS_RESPONSE = {
    "data": [
        {
            "hotel": {
                "hotelId": "HTLX0001",
                "name": "Grand Tokyo Hotel",
                "rating": "4",
            },
            "offers": [
                {
                    "price": {"total": "800.00", "currency": "USD"},
                    "policies": {
                        "cancellations": [
                            {"type": "FULL_REFUNDABLE", "deadline": "2026-04-30T23:59:00"}
                        ]
                    },
                }
            ],
        },
        {
            "hotel": {
                "hotelId": "HTLX0002",
                "name": "Budget Inn Tokyo",
                "rating": "2",
            },
            "offers": [
                {
                    "price": {"total": "300.00", "currency": "USD"},
                    "policies": {},
                }
            ],
        },
    ]
}


class TestAmadeusHotelSource:

    @pytest.mark.anyio
    async def test_is_available_with_keys(self, source: AmadeusHotelSource):
        assert await source.is_available()

    @pytest.mark.anyio
    async def test_is_unavailable_without_keys(self):
        src = AmadeusHotelSource(AmadeusConfig())
        assert not await src.is_available()

    @pytest.mark.anyio
    @respx.mock
    async def test_two_step_search(self, source: AmadeusHotelSource):
        respx.post("https://test.api.amadeus.com/v1/security/oauth2/token").mock(
            return_value=httpx.Response(200, json=TOKEN_RESPONSE),
        )
        respx.get(
            "https://test.api.amadeus.com/v1/reference-data/locations/hotels/by-city"
        ).mock(return_value=httpx.Response(200, json=HOTEL_LIST_RESPONSE))

        respx.get(
            "https://test.api.amadeus.com/v3/shopping/hotel-offers"
        ).mock(return_value=httpx.Response(200, json=HOTEL_OFFERS_RESPONSE))

        results = await source.search_hotels("Tokyo", "2026-05-01", "2026-05-05")
        await source.close()

        assert len(results) == 2
        # Sorted by price
        assert results[0]["price_per_night_usd"] <= results[1]["price_per_night_usd"]

    @pytest.mark.anyio
    @respx.mock
    async def test_normalisation(self, source: AmadeusHotelSource):
        respx.post("https://test.api.amadeus.com/v1/security/oauth2/token").mock(
            return_value=httpx.Response(200, json=TOKEN_RESPONSE),
        )
        respx.get(
            "https://test.api.amadeus.com/v1/reference-data/locations/hotels/by-city"
        ).mock(return_value=httpx.Response(200, json=HOTEL_LIST_RESPONSE))
        respx.get(
            "https://test.api.amadeus.com/v3/shopping/hotel-offers"
        ).mock(return_value=httpx.Response(200, json=HOTEL_OFFERS_RESPONSE))

        results = await source.search_hotels("Tokyo", "2026-05-01", "2026-05-05")
        await source.close()

        first = results[0]
        assert first["source"] == "amadeus"
        assert first["city"] == "Tokyo"
        assert first["check_in"] == "2026-05-01"
        assert first["check_out"] == "2026-05-05"
        assert first["total_nights"] == 4

    @pytest.mark.anyio
    @respx.mock
    async def test_api_error_returns_empty(self, source: AmadeusHotelSource):
        respx.post("https://test.api.amadeus.com/v1/security/oauth2/token").mock(
            return_value=httpx.Response(200, json=TOKEN_RESPONSE),
        )
        respx.get(
            "https://test.api.amadeus.com/v1/reference-data/locations/hotels/by-city"
        ).mock(return_value=httpx.Response(500))

        results = await source.search_hotels("Tokyo", "2026-05-01", "2026-05-05")
        await source.close()
        assert results == []
