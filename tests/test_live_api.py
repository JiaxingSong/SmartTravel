"""Live API smoke tests — only run when SMARTTRAVEL_TEST_LIVE=1.

These tests hit real (sandbox) API endpoints.  Each source has its own
skip marker that checks the corresponding API-key env var, so you can
run a partial suite.

Usage
-----
::

    SMARTTRAVEL_TEST_LIVE=1 \
    AMADEUS_API_KEY=xxx AMADEUS_API_SECRET=yyy AMADEUS_ENVIRONMENT=test \
    TICKETMASTER_API_KEY=www \
    pytest tests/test_live_api.py -v
"""

from __future__ import annotations

import os

import pytest

from smart_travel.config import (
    AmadeusConfig,
    AppConfig,
    TicketmasterConfig,
)
from smart_travel.data.resolver import (
    search_flights,
    search_hotels,
    set_cache,
    set_registry,
)
from smart_travel.data.sources.flights.amadeus import AmadeusFlightSource
from smart_travel.data.sources.hotels.amadeus import AmadeusHotelSource
from smart_travel.data.sources.registry import SourceRegistry
from smart_travel.data.sources.tickets.ticketmaster import TicketmasterSource

# ---- Module-level skip: no live tests unless explicitly opted-in ----

pytestmark = pytest.mark.skipif(
    not os.environ.get("SMARTTRAVEL_TEST_LIVE"),
    reason="Set SMARTTRAVEL_TEST_LIVE=1 to run live API tests",
)

# ---- Per-source conditional skip markers ----

requires_amadeus = pytest.mark.skipif(
    not (os.environ.get("AMADEUS_API_KEY") and os.environ.get("AMADEUS_API_SECRET")),
    reason="AMADEUS_API_KEY + AMADEUS_API_SECRET required",
)

requires_ticketmaster = pytest.mark.skipif(
    not os.environ.get("TICKETMASTER_API_KEY"),
    reason="TICKETMASTER_API_KEY required",
)


# ---- Helpers ----

def _amadeus_config_from_env() -> AmadeusConfig:
    return AmadeusConfig(
        api_key=os.environ.get("AMADEUS_API_KEY", ""),
        api_secret=os.environ.get("AMADEUS_API_SECRET", ""),
        environment=os.environ.get("AMADEUS_ENVIRONMENT", "test"),
    )


def _ticketmaster_config_from_env() -> TicketmasterConfig:
    return TicketmasterConfig(
        api_key=os.environ.get("TICKETMASTER_API_KEY", ""),
    )


# ---- autouse reset ----

@pytest.fixture(autouse=True)
def _reset_resolver():
    set_registry(None)  # type: ignore[arg-type]
    set_cache(None)  # type: ignore[arg-type]
    yield
    set_registry(None)  # type: ignore[arg-type]
    set_cache(None)  # type: ignore[arg-type]


# =====================================================================
# Amadeus Live Flights
# =====================================================================

@requires_amadeus
class TestAmadeusLiveFlights:

    @pytest.mark.anyio
    async def test_basic_search_returns_results(self):
        config = _amadeus_config_from_env()
        source = AmadeusFlightSource(config)
        try:
            results = await source.search_flights(
                "Seattle", "Tokyo", "2026-09-01",
            )
        finally:
            await source.close()

        assert len(results) > 0
        for r in results:
            assert r["price_usd"] > 0
            assert r["flight_number"]
            assert r["airline"]
            assert r["source"] == "amadeus"

    @pytest.mark.anyio
    async def test_round_trip_search(self):
        config = _amadeus_config_from_env()
        source = AmadeusFlightSource(config)
        try:
            results = await source.search_flights(
                "Seattle", "Tokyo", "2026-09-01",
                return_date="2026-09-15",
            )
        finally:
            await source.close()

        # Should not raise; results is a list (may be empty depending
        # on sandbox data, but the call itself should succeed)
        assert isinstance(results, list)


# =====================================================================
# Amadeus Live Hotels
# =====================================================================

@requires_amadeus
class TestAmadeusLiveHotels:

    @pytest.mark.anyio
    async def test_basic_search_returns_results(self):
        config = _amadeus_config_from_env()
        source = AmadeusHotelSource(config)
        try:
            results = await source.search_hotels(
                "Tokyo", "2026-09-01", "2026-09-05",
            )
        finally:
            await source.close()

        assert len(results) > 0
        for r in results:
            assert r["price_per_night_usd"] > 0
            assert r["name"]
            assert r["source"] == "amadeus"


# =====================================================================
# Ticketmaster Live
# =====================================================================

@requires_ticketmaster
class TestTicketmasterLive:

    @pytest.mark.anyio
    async def test_basic_search_returns_results(self):
        config = _ticketmaster_config_from_env()
        source = TicketmasterSource(config)
        try:
            results = await source.search_tickets(
                "New York", "2026-09-01", "2026-09-30",
            )
        finally:
            await source.close()

        assert len(results) > 0
        for r in results:
            assert r["name"]
            assert r["date"]
            assert r["source"] == "ticketmaster"
            assert r["average_price_usd"] > 0


# =====================================================================
# Full pipeline with live Amadeus
# =====================================================================

@requires_amadeus
class TestLiveFullPipeline:

    @pytest.mark.anyio
    async def test_resolver_with_live_amadeus_flights(self):
        """Resolver picks up live Amadeus source and tags _data_quality."""
        config = AppConfig(amadeus=_amadeus_config_from_env())
        set_registry(SourceRegistry(config))

        results = await search_flights("Seattle", "Tokyo", "2026-09-01")

        # Results may come from live or mock; all should be tagged
        for r in results:
            assert "_data_quality" in r

    @pytest.mark.anyio
    async def test_resolver_with_live_amadeus_hotels(self):
        """Resolver picks up live Amadeus hotel source and tags _data_quality."""
        config = AppConfig(amadeus=_amadeus_config_from_env())
        set_registry(SourceRegistry(config))

        results = await search_hotels("Tokyo", "2026-09-01", "2026-09-05")

        for r in results:
            assert "_data_quality" in r
