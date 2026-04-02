"""Shared test fixtures for SmartTravel."""

from __future__ import annotations

import pytest

from smart_travel.config import (
    AmadeusConfig,
    AppConfig,
    BrowserConfig,
    CacheConfig,
    MemoryConfig,
    PostgresConfig,
    SeatsAeroConfig,
    TicketmasterConfig,
)


@pytest.fixture
def amadeus_config() -> AmadeusConfig:
    """Amadeus config with test keys."""
    return AmadeusConfig(
        api_key="test_key",
        api_secret="test_secret",
        environment="test",
    )


@pytest.fixture
def seats_aero_config() -> SeatsAeroConfig:
    """seats.aero config with test key."""
    return SeatsAeroConfig(api_key="test_partner_key")


@pytest.fixture
def ticketmaster_config() -> TicketmasterConfig:
    """Ticketmaster config with test key."""
    return TicketmasterConfig(api_key="test_tm_key")


@pytest.fixture
def full_config(
    amadeus_config: AmadeusConfig,
    seats_aero_config: SeatsAeroConfig,
    ticketmaster_config: TicketmasterConfig,
) -> AppConfig:
    """App config with all API keys configured."""
    return AppConfig(
        amadeus=amadeus_config,
        seats_aero=seats_aero_config,
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
