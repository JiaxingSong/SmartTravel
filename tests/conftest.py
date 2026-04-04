"""Shared test fixtures for SmartTravel."""

from __future__ import annotations

import httpx
import pytest
import respx

from smart_travel.config import (
    AmadeusConfig,
    AppConfig,
    BrowserConfig,
    CacheConfig,
    MemoryConfig,
    PostgresConfig,
    TicketmasterConfig,
)

# Re-use response payloads from existing source-level tests
from tests.test_sources.test_amadeus_flights import (
    FLIGHT_OFFERS_RESPONSE,
    TOKEN_RESPONSE as AMADEUS_TOKEN_RESPONSE,
)
from tests.test_sources.test_amadeus_hotels import (
    HOTEL_LIST_RESPONSE,
    HOTEL_OFFERS_RESPONSE,
    TOKEN_RESPONSE as AMADEUS_HOTEL_TOKEN_RESPONSE,
)
from tests.test_sources.test_ticketmaster import EVENTS_RESPONSE


@pytest.fixture
def amadeus_config() -> AmadeusConfig:
    """Amadeus config with test keys."""
    return AmadeusConfig(
        api_key="test_key",
        api_secret="test_secret",
        environment="test",
    )


@pytest.fixture
def ticketmaster_config() -> TicketmasterConfig:
    """Ticketmaster config with test key."""
    return TicketmasterConfig(api_key="test_tm_key")


@pytest.fixture
def full_config(
    amadeus_config: AmadeusConfig,
    ticketmaster_config: TicketmasterConfig,
) -> AppConfig:
    """App config with all API keys configured."""
    return AppConfig(
        amadeus=amadeus_config,
        ticketmaster=ticketmaster_config,
        browser=BrowserConfig(),
        cache=CacheConfig(),
        memory=MemoryConfig(),
        postgres=PostgresConfig(),
    )


@pytest.fixture
def no_keys_config() -> AppConfig:
    """App config with *no* API keys (everything falls back to mock)."""
    return AppConfig()


# ---------------------------------------------------------------------------
# Shared respx mock fixtures for integration tests
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_all_flight_apis() -> dict[str, respx.Route]:
    """Register respx routes for Amadeus flights.

    Returns a dict of named routes for call-count inspection.
    Callers must still activate respx (``@respx.mock`` decorator or context).
    """
    token_route = respx.post(
        "https://test.api.amadeus.com/v1/security/oauth2/token",
    ).mock(return_value=httpx.Response(200, json=AMADEUS_TOKEN_RESPONSE))

    flights_route = respx.get(
        "https://test.api.amadeus.com/v2/shopping/flight-offers",
    ).mock(return_value=httpx.Response(200, json=FLIGHT_OFFERS_RESPONSE))

    return {
        "token": token_route,
        "flights": flights_route,
    }


@pytest.fixture
def mock_all_hotel_apis() -> dict[str, respx.Route]:
    """Register respx routes for Amadeus hotel-list + hotel-offers.

    Returns a dict of named routes for call-count inspection.
    """
    token_route = respx.post(
        "https://test.api.amadeus.com/v1/security/oauth2/token",
    ).mock(return_value=httpx.Response(200, json=AMADEUS_HOTEL_TOKEN_RESPONSE))

    hotel_list_route = respx.get(
        "https://test.api.amadeus.com/v1/reference-data/locations/hotels/by-city",
    ).mock(return_value=httpx.Response(200, json=HOTEL_LIST_RESPONSE))

    hotel_offers_route = respx.get(
        "https://test.api.amadeus.com/v3/shopping/hotel-offers",
    ).mock(return_value=httpx.Response(200, json=HOTEL_OFFERS_RESPONSE))

    return {
        "token": token_route,
        "hotel_list": hotel_list_route,
        "hotel_offers": hotel_offers_route,
    }


@pytest.fixture
def mock_all_ticket_apis() -> dict[str, respx.Route]:
    """Register respx routes for Ticketmaster events.

    Returns a dict of named routes for call-count inspection.
    """
    events_route = respx.get(
        "https://app.ticketmaster.com/discovery/v2/events.json",
    ).mock(return_value=httpx.Response(200, json=EVENTS_RESPONSE))

    return {"events": events_route}
