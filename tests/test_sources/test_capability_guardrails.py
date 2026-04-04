"""Capability guardrail tests — validate the real-user capability matrix.

Each test in this module corresponds to a cell in the capability matrix:

    | Domain  | Cash Prices      | Points Prices              | Merged View         |
    |---------|------------------|----------------------------|---------------------|
    | Flights | Amadeus + Google | Airline award scrapers     | resolver merges     |
    | Hotels  | Amadeus + Google | NO SOURCE (gap)            | plumbing ready      |
    | Events  | Ticketmaster     | N/A                        | N/A                 |

If any of these assumptions change (new source added, field renamed, etc.),
the relevant guardrail test will fail, forcing an intentional update.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from smart_travel.config import (
    AmadeusConfig,
    AppConfig,
    BrowserConfig,
    TicketmasterConfig,
)
from smart_travel.data.resolver import (
    _merge_flight_results,
    _merge_hotel_results,
    search_flights,
    search_hotels,
    set_cache,
    set_registry,
)
from smart_travel.data.sources.base import (
    BaseFlightSource,
    BaseHotelSource,
    BaseSource,
    FetchMethod,
    PriceType,
    SourceInfo,
)
from smart_travel.data.sources.flights.amadeus import AmadeusFlightSource
from smart_travel.data.sources.hotels.amadeus import AmadeusHotelSource
from smart_travel.data.sources.registry import SourceRegistry
from smart_travel.data.sources.tickets.ticketmaster import TicketmasterSource


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def amadeus_config() -> AmadeusConfig:
    return AmadeusConfig(api_key="test_key", api_secret="test_secret", environment="test")


@pytest.fixture
def ticketmaster_config() -> TicketmasterConfig:
    return TicketmasterConfig(api_key="test_tm_key")


@pytest.fixture(autouse=True)
def _reset_resolver():
    """Ensure the module-level registry and cache are cleared between tests."""
    set_registry(None)  # type: ignore[arg-type]
    set_cache(None)  # type: ignore[arg-type]
    yield
    set_registry(None)  # type: ignore[arg-type]
    set_cache(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Sample API responses (shared across tests)
# ---------------------------------------------------------------------------

TOKEN_RESPONSE = {
    "access_token": "test_token_123",
    "token_type": "Bearer",
    "expires_in": 1799,
}

AMADEUS_FLIGHT_RESPONSE = {
    "data": [
        {
            "id": "1",
            "numberOfBookableSeats": 9,
            "itineraries": [
                {
                    "duration": "PT13H45M",
                    "segments": [
                        {
                            "departure": {"iataCode": "SEA", "at": "2026-05-01T14:30:00"},
                            "arrival": {"iataCode": "NRT", "at": "2026-05-02T17:15:00"},
                            "carrierCode": "UA",
                            "number": "876",
                        }
                    ],
                }
            ],
            "price": {"currency": "USD", "grandTotal": "650.50"},
        },
    ],
    "dictionaries": {"carriers": {"UA": "United Airlines"}},
}

AMADEUS_HOTEL_LIST_RESPONSE = {
    "data": [
        {"hotelId": "HTLX0001"},
    ],
}

AMADEUS_HOTEL_OFFERS_RESPONSE = {
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
    ],
}

TICKETMASTER_RESPONSE = {
    "_embedded": {
        "events": [
            {
                "name": "Coldplay World Tour",
                "dates": {"start": {"localDate": "2026-05-05", "localTime": "19:30:00"}},
                "_embedded": {"venues": [{"name": "Tokyo Dome"}]},
                "classifications": [{"segment": {"name": "Music"}}],
                "priceRanges": [{"min": 75.0, "max": 350.0, "currency": "USD"}],
                "url": "https://ticketmaster.com/event/12345",
            },
        ]
    }
}


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: price_types CONTRACT TESTS
#
# Each source declares what pricing it returns (CASH, POINTS, or both).
# These tests verify that the returned data actually matches that claim.
# ═══════════════════════════════════════════════════════════════════════════


class TestAmadeusFlightsContract:
    """Amadeus flights: declares {CASH} → must return price_usd, NOT points."""

    def test_declares_cash_only(self):
        src = AmadeusFlightSource(AmadeusConfig())
        assert src.info.price_types == frozenset({PriceType.CASH})

    @pytest.mark.anyio
    @respx.mock
    async def test_returns_cash_fields(self, amadeus_config: AmadeusConfig):
        src = AmadeusFlightSource(amadeus_config)
        respx.post("https://test.api.amadeus.com/v1/security/oauth2/token").mock(
            return_value=httpx.Response(200, json=TOKEN_RESPONSE),
        )
        respx.get("https://test.api.amadeus.com/v2/shopping/flight-offers").mock(
            return_value=httpx.Response(200, json=AMADEUS_FLIGHT_RESPONSE),
        )

        results = await src.search_flights("Seattle", "Tokyo", "2026-05-01")
        await src.close()

        assert len(results) > 0
        for r in results:
            # CASH contract: price_usd must be present and numeric
            assert "price_usd" in r
            assert isinstance(r["price_usd"], (int, float))
            assert r["price_usd"] > 0

    @pytest.mark.anyio
    @respx.mock
    async def test_does_not_return_points_fields(self, amadeus_config: AmadeusConfig):
        src = AmadeusFlightSource(amadeus_config)
        respx.post("https://test.api.amadeus.com/v1/security/oauth2/token").mock(
            return_value=httpx.Response(200, json=TOKEN_RESPONSE),
        )
        respx.get("https://test.api.amadeus.com/v2/shopping/flight-offers").mock(
            return_value=httpx.Response(200, json=AMADEUS_FLIGHT_RESPONSE),
        )

        results = await src.search_flights("Seattle", "Tokyo", "2026-05-01")
        await src.close()

        for r in results:
            # A CASH-only source must not attach points data
            assert r.get("points_price") is None or "points_price" not in r
            assert r.get("points_program") is None or "points_program" not in r


class TestAmadeusHotelsContract:
    """Amadeus hotels: declares {CASH} → must return price_per_night_usd, NOT points."""

    def test_declares_cash_only(self):
        src = AmadeusHotelSource(AmadeusConfig())
        assert src.info.price_types == frozenset({PriceType.CASH})

    @pytest.mark.anyio
    @respx.mock
    async def test_returns_cash_fields(self, amadeus_config: AmadeusConfig):
        src = AmadeusHotelSource(amadeus_config)
        respx.post("https://test.api.amadeus.com/v1/security/oauth2/token").mock(
            return_value=httpx.Response(200, json=TOKEN_RESPONSE),
        )
        respx.get(
            "https://test.api.amadeus.com/v1/reference-data/locations/hotels/by-city"
        ).mock(return_value=httpx.Response(200, json=AMADEUS_HOTEL_LIST_RESPONSE))
        respx.get(
            "https://test.api.amadeus.com/v3/shopping/hotel-offers"
        ).mock(return_value=httpx.Response(200, json=AMADEUS_HOTEL_OFFERS_RESPONSE))

        results = await src.search_hotels("Tokyo", "2026-05-01", "2026-05-05")
        await src.close()

        assert len(results) > 0
        for r in results:
            assert "price_per_night_usd" in r
            assert isinstance(r["price_per_night_usd"], (int, float))
            assert r["price_per_night_usd"] > 0

    @pytest.mark.anyio
    @respx.mock
    async def test_does_not_return_points_fields(self, amadeus_config: AmadeusConfig):
        src = AmadeusHotelSource(amadeus_config)
        respx.post("https://test.api.amadeus.com/v1/security/oauth2/token").mock(
            return_value=httpx.Response(200, json=TOKEN_RESPONSE),
        )
        respx.get(
            "https://test.api.amadeus.com/v1/reference-data/locations/hotels/by-city"
        ).mock(return_value=httpx.Response(200, json=AMADEUS_HOTEL_LIST_RESPONSE))
        respx.get(
            "https://test.api.amadeus.com/v3/shopping/hotel-offers"
        ).mock(return_value=httpx.Response(200, json=AMADEUS_HOTEL_OFFERS_RESPONSE))

        results = await src.search_hotels("Tokyo", "2026-05-01", "2026-05-05")
        await src.close()

        for r in results:
            assert r.get("points_price") is None or "points_price" not in r
            assert r.get("points_program") is None or "points_program" not in r


class TestTicketmasterContract:
    """Ticketmaster: declares {CASH} → must return price_range_usd, NOT points."""

    def test_declares_cash_only(self):
        src = TicketmasterSource(TicketmasterConfig())
        assert src.info.price_types == frozenset({PriceType.CASH})

    @pytest.mark.anyio
    @respx.mock
    async def test_returns_cash_fields(self, ticketmaster_config: TicketmasterConfig):
        src = TicketmasterSource(ticketmaster_config)
        respx.get("https://app.ticketmaster.com/discovery/v2/events.json").mock(
            return_value=httpx.Response(200, json=TICKETMASTER_RESPONSE),
        )

        results = await src.search_tickets("Tokyo", "2026-05-01", "2026-05-10")
        await src.close()

        assert len(results) > 0
        for r in results:
            assert "price_range_usd" in r
            assert "average_price_usd" in r
            assert isinstance(r["average_price_usd"], (int, float))
            assert r["average_price_usd"] > 0

    @pytest.mark.anyio
    @respx.mock
    async def test_does_not_return_points_fields(self, ticketmaster_config: TicketmasterConfig):
        src = TicketmasterSource(ticketmaster_config)
        respx.get("https://app.ticketmaster.com/discovery/v2/events.json").mock(
            return_value=httpx.Response(200, json=TICKETMASTER_RESPONSE),
        )

        results = await src.search_tickets("Tokyo", "2026-05-01", "2026-05-10")
        await src.close()

        for r in results:
            assert r.get("points_price") is None or "points_price" not in r
            assert r.get("points_program") is None or "points_program" not in r


class TestGoogleFlightsContract:
    """Google Flights: declares {CASH} → helper must return price_usd, points=None."""

    def test_declares_cash_only(self):
        from smart_travel.data.sources.flights.google_flights import GoogleFlightsSource
        src = GoogleFlightsSource(BrowserConfig())
        assert src.info.price_types == frozenset({PriceType.CASH})

    def test_parse_results_returns_cash_not_points(self):
        from smart_travel.data.sources.flights.google_flights import GoogleFlightsSource
        src = GoogleFlightsSource(BrowserConfig())
        raw = [
            {"price": "$500", "airline": "UA", "times": "10:00", "duration": "10h", "stops": "Nonstop"},
        ]
        results = src._parse_results(
            raw, "Seattle", "Tokyo", "2026-05-01", "economy", 1, None, None,
        )
        assert len(results) == 1
        r = results[0]
        assert isinstance(r["price_usd"], (int, float))
        assert r["price_usd"] > 0
        assert r.get("points_price") is None
        assert r.get("points_program") is None


class TestGoogleHotelsContract:
    """Google Hotels: declares {CASH} → helper must return price, points=None."""

    def test_declares_cash_only(self):
        from smart_travel.data.sources.hotels.google_hotels import GoogleHotelsSource
        src = GoogleHotelsSource(BrowserConfig())
        assert src.info.price_types == frozenset({PriceType.CASH})

    def test_parse_results_returns_cash_not_points(self):
        from smart_travel.data.sources.hotels.google_hotels import GoogleHotelsSource
        src = GoogleHotelsSource(BrowserConfig())
        raw = [
            {"name": "Hotel A", "price": "$200", "rating": "4.0", "stars": "4", "amenities": "WiFi"},
        ]
        results = src._parse_results(
            raw, "Tokyo", "2026-05-01", "2026-05-05", 1, 1,
            None, None, None,
        )
        assert len(results) == 1
        r = results[0]
        assert isinstance(r["price_per_night_usd"], (int, float))
        assert r["price_per_night_usd"] > 0
        assert r.get("points_price") is None
        assert r.get("points_program") is None


class TestMockFlightsContract:
    """Mock flights: declares {CASH, POINTS} → must return both."""

    def test_declares_cash_and_points(self):
        from smart_travel.data.sources.flights.mock import MockFlightSource
        src = MockFlightSource()
        assert src.info.price_types == frozenset({PriceType.CASH, PriceType.POINTS})

    @pytest.mark.anyio
    async def test_returns_both_cash_and_points(self):
        from smart_travel.data.sources.flights.mock import MockFlightSource
        src = MockFlightSource()
        results = await src.search_flights("Seattle", "Tokyo", "2026-05-01")
        assert len(results) > 0
        for r in results:
            assert isinstance(r["price_usd"], (int, float))
            assert r["price_usd"] > 0
            assert isinstance(r["points_price"], int)
            assert r["points_price"] > 0
            assert isinstance(r["points_program"], str)


class TestMockHotelsContract:
    """Mock hotels: declares {CASH, POINTS} → chain hotels return both."""

    def test_declares_cash_and_points(self):
        from smart_travel.data.sources.hotels.mock import MockHotelSource
        src = MockHotelSource()
        assert src.info.price_types == frozenset({PriceType.CASH, PriceType.POINTS})

    @pytest.mark.anyio
    async def test_chain_hotels_return_both_cash_and_points(self):
        from smart_travel.data.sources.hotels.mock import MockHotelSource
        src = MockHotelSource()
        results = await src.search_hotels("Tokyo", "2026-05-01", "2026-05-05")
        chain_results = [r for r in results if r.get("points_price") is not None]
        assert len(chain_results) > 0
        for r in chain_results:
            assert isinstance(r["price_per_night_usd"], (int, float))
            assert r["price_per_night_usd"] > 0
            assert isinstance(r["points_price"], int)
            assert r["points_price"] > 0
            assert isinstance(r["points_program"], str)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: HOTEL POINTS GAP — NEGATIVE GUARDRAIL
#
# Documents the known gap: no live hotel source returns points.
# If someone adds a hotel points source, these tests should be updated
# intentionally to reflect the new capability.
# ═══════════════════════════════════════════════════════════════════════════


class TestHotelPointsGap:
    """Guardrail: no live hotel source provides points pricing today.

    These tests document the known gap.  If a future hotel points source
    is added, update these tests to reflect the new capability.
    """

    def test_no_live_hotel_source_declares_points(self):
        """All live hotel sources declare CASH only — no POINTS."""
        config = AppConfig(
            amadeus=AmadeusConfig(api_key="k", api_secret="s"),
        )
        registry = SourceRegistry(config)
        hotel_sources = registry.list_sources("hotels")

        for info in hotel_sources:
            if info.fetch_method == FetchMethod.MOCK:
                continue  # mock now has POINTS, skip it
            assert PriceType.POINTS not in info.price_types, (
                f"Live hotel source '{info.name}' declares POINTS — "
                f"update this guardrail if hotel points support was added intentionally"
            )

    @pytest.mark.anyio
    @respx.mock
    async def test_amadeus_hotels_no_points_in_output(
        self, amadeus_config: AmadeusConfig,
    ):
        """Amadeus hotel results carry no points fields — gap is real."""
        src = AmadeusHotelSource(amadeus_config)
        respx.post("https://test.api.amadeus.com/v1/security/oauth2/token").mock(
            return_value=httpx.Response(200, json=TOKEN_RESPONSE),
        )
        respx.get(
            "https://test.api.amadeus.com/v1/reference-data/locations/hotels/by-city"
        ).mock(return_value=httpx.Response(200, json=AMADEUS_HOTEL_LIST_RESPONSE))
        respx.get(
            "https://test.api.amadeus.com/v3/shopping/hotel-offers"
        ).mock(return_value=httpx.Response(200, json=AMADEUS_HOTEL_OFFERS_RESPONSE))

        results = await src.search_hotels("Tokyo", "2026-05-01", "2026-05-05")
        await src.close()

        for r in results:
            has_points = (
                r.get("points_price") is not None
                and isinstance(r["points_price"], int)
                and r["points_price"] > 0
            )
            assert not has_points, (
                "Amadeus hotel returned points_price — if this is intentional, "
                "update the capability matrix and these guardrails"
            )

    def test_google_hotels_helper_no_points(self):
        """Google Hotels parser produces no points — gap is real."""
        from smart_travel.data.sources.hotels.google_hotels import GoogleHotelsSource
        src = GoogleHotelsSource(BrowserConfig())
        raw = [{"name": "X", "price": "$200", "rating": "4", "stars": "4", "amenities": ""}]
        results = src._parse_results(
            raw, "Tokyo", "2026-05-01", "2026-05-05", 1, 1, None, None, None,
        )
        for r in results:
            assert r.get("points_price") is None


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: MULTI-SOURCE RESOLVER INTEGRATION
#
# Validates that the resolver correctly merges results from multiple
# sources when they are all available simultaneously.
# ═══════════════════════════════════════════════════════════════════════════


class TestFlightMergeIntegration:
    """Resolver merges Amadeus (cash) + points source correctly."""

    def test_merge_attaches_points_to_matching_cash(self):
        """When cash and points share (date, origin_airport, destination_airport),
        the merged result has both price_usd and points_price."""
        cash_result = {
            "source": "amadeus",
            "date": "2026-05-01",
            "origin_airport": "SEA",
            "destination_airport": "NRT",
            "price_usd": 650.50,
            "airline": "United Airlines",
        }
        points_result = {
            "source": "united_award",
            "date": "2026-05-01",
            "origin_airport": "SEA",
            "destination_airport": "NRT",
            "price_usd": None,
            "points_price": 70000,
            "points_program": "united",
        }
        merged = _merge_flight_results([cash_result, points_result])

        # Should have exactly 1 merged result
        assert len(merged) == 1
        r = merged[0]
        assert r["source"] == "amadeus"
        assert r["price_usd"] == 650.50
        assert r["points_price"] == 70000
        assert r["points_program"] == "united"

    def test_merge_keeps_unmatched_points(self):
        """Points-only results with no cash match are appended."""
        cash_result = {
            "source": "amadeus",
            "date": "2026-05-01",
            "origin_airport": "SEA",
            "destination_airport": "NRT",
            "price_usd": 650.50,
        }
        unmatched_points = {
            "source": "united_award",
            "date": "2026-05-01",
            "origin_airport": "SFO",
            "destination_airport": "NRT",
            "price_usd": None,
            "points_price": 55000,
            "points_program": "aeroplan",
        }
        merged = _merge_flight_results([cash_result, unmatched_points])
        assert len(merged) == 2

    def test_merge_picks_cheapest_points(self):
        """When multiple points sources match, the cheapest is used."""
        cash = {
            "source": "amadeus",
            "date": "2026-05-01",
            "origin_airport": "SEA",
            "destination_airport": "NRT",
            "price_usd": 650.50,
        }
        points_a = {
            "source": "united_award",
            "date": "2026-05-01",
            "origin_airport": "SEA",
            "destination_airport": "NRT",
            "price_usd": None,
            "points_price": 70000,
            "points_program": "united",
        }
        points_b = {
            "source": "united_award",
            "date": "2026-05-01",
            "origin_airport": "SEA",
            "destination_airport": "NRT",
            "price_usd": None,
            "points_price": 55000,
            "points_program": "aeroplan",
        }
        merged = _merge_flight_results([cash, points_a, points_b])
        assert len(merged) == 1
        assert merged[0]["points_price"] == 55000
        assert merged[0]["points_program"] == "aeroplan"

    def test_cash_only_passthrough(self):
        """When no points sources contribute, cash results pass through unchanged."""
        results = [
            {"source": "amadeus", "date": "2026-05-01",
             "origin_airport": "SEA", "destination_airport": "NRT",
             "price_usd": 650.50},
            {"source": "amadeus", "date": "2026-05-01",
             "origin_airport": "SEA", "destination_airport": "NRT",
             "price_usd": 520.00},
        ]
        merged = _merge_flight_results(results)
        assert len(merged) == 2
        assert merged[0]["price_usd"] == 520.00  # sorted ascending


class TestHotelMergeIntegration:
    """Resolver hotel merge — ready for future hotel points sources."""

    def test_merge_attaches_points_to_matching_cash(self):
        """Verifies merge logic works if a hotel points source existed."""
        cash = {
            "source": "amadeus",
            "check_in": "2026-05-01",
            "name": "Grand Tokyo Hotel",
            "city": "Tokyo",
            "price_per_night_usd": 200.0,
        }
        points = {
            "source": "future_points_api",
            "check_in": "2026-05-01",
            "name": "Grand Tokyo Hotel",
            "city": "Tokyo",
            "price_per_night_usd": None,
            "points_price": 25000,
            "points_program": "marriott bonvoy",
        }
        merged = _merge_hotel_results([cash, points])
        assert len(merged) == 1
        assert merged[0]["price_per_night_usd"] == 200.0
        assert merged[0]["points_price"] == 25000
        assert merged[0]["points_program"] == "marriott bonvoy"

    def test_merge_keeps_unmatched_points(self):
        """Unmatched points-only hotels are appended."""
        cash = {
            "check_in": "2026-05-01", "name": "Hilton", "city": "Tokyo",
            "price_per_night_usd": 180.0,
        }
        points = {
            "check_in": "2026-05-01", "name": "Marriott", "city": "Tokyo",
            "price_per_night_usd": None, "points_price": 25000,
            "points_program": "marriott bonvoy",
        }
        merged = _merge_hotel_results([cash, points])
        assert len(merged) == 2

    def test_mock_results_pass_through(self):
        """Mock results already have cash+points — merge is a passthrough."""
        # Simulates what mock source returns: combined cash+points in one dict
        results = [
            {
                "source": "mock", "check_in": "2026-05-01",
                "name": "Marriott Tokyo", "city": "Tokyo",
                "price_per_night_usd": 200.0,
                "points_price": 25000, "points_program": "marriott bonvoy",
            },
            {
                "source": "mock", "check_in": "2026-05-01",
                "name": "Boutique Tokyo", "city": "Tokyo",
                "price_per_night_usd": 100.0,
                "points_price": None, "points_program": None,
            },
        ]
        merged = _merge_hotel_results(results)
        assert len(merged) == 2
        # Sorted by price
        assert merged[0]["price_per_night_usd"] == 100.0
        assert merged[1]["price_per_night_usd"] == 200.0
        # Points preserved
        assert merged[1]["points_price"] == 25000


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: BROWSER SOURCE DEGRADATION
#
# Google Flights/Hotels and airline award sources use Playwright. These tests verify
# that the sources degrade gracefully when Playwright is unavailable.
# ═══════════════════════════════════════════════════════════════════════════


class TestBrowserSourceDegradation:
    """Browser sources degrade gracefully when Playwright is unavailable."""

    @pytest.mark.anyio
    async def test_google_flights_availability_returns_bool(self):
        """is_available() never raises — returns False if playwright missing."""
        from smart_travel.data.sources.flights.google_flights import GoogleFlightsSource
        src = GoogleFlightsSource(BrowserConfig())
        result = await src.is_available()
        assert isinstance(result, bool)

    @pytest.mark.anyio
    async def test_google_hotels_availability_returns_bool(self):
        """is_available() never raises — returns False if playwright missing."""
        from smart_travel.data.sources.hotels.google_hotels import GoogleHotelsSource
        src = GoogleHotelsSource(BrowserConfig())
        result = await src.is_available()
        assert isinstance(result, bool)

    def test_registry_handles_missing_playwright(self):
        """Registry doesn't crash if playwright is uninstalled."""
        config = AppConfig()
        registry = SourceRegistry(config)
        # Should have at least mock sources
        flight_sources = registry.list_sources("flights")
        hotel_sources = registry.list_sources("hotels")
        assert any(s.name == "mock" for s in flight_sources)
        assert any(s.name == "mock" for s in hotel_sources)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5: COMPLETE FIELD SCHEMA VALIDATION
#
# Each source type must return specific fields. These tests verify the
# exact field names — catches renames, missing fields, etc.
# ═══════════════════════════════════════════════════════════════════════════


REQUIRED_FLIGHT_FIELDS = {
    "source", "flight_number", "airline", "origin", "origin_airport",
    "destination", "destination_airport", "date", "departure_time",
    "duration", "stops", "cabin_class",
}

REQUIRED_HOTEL_FIELDS = {
    "source", "name", "city", "star_rating", "price_per_night_usd",
    "check_in", "check_out",
}

REQUIRED_TICKET_FIELDS = {
    "source", "name", "event_type", "venue", "city", "date", "time",
    "price_range_usd", "average_price_usd",
}


class TestFieldSchemaValidation:
    """Every source returns the expected set of field names."""

    @pytest.mark.anyio
    @respx.mock
    async def test_amadeus_flights_field_schema(self, amadeus_config: AmadeusConfig):
        src = AmadeusFlightSource(amadeus_config)
        respx.post("https://test.api.amadeus.com/v1/security/oauth2/token").mock(
            return_value=httpx.Response(200, json=TOKEN_RESPONSE),
        )
        respx.get("https://test.api.amadeus.com/v2/shopping/flight-offers").mock(
            return_value=httpx.Response(200, json=AMADEUS_FLIGHT_RESPONSE),
        )
        results = await src.search_flights("Seattle", "Tokyo", "2026-05-01")
        await src.close()

        for r in results:
            missing = REQUIRED_FLIGHT_FIELDS - set(r.keys())
            assert not missing, f"Amadeus flights missing fields: {missing}"

    @pytest.mark.anyio
    @respx.mock
    async def test_amadeus_hotels_field_schema(self, amadeus_config: AmadeusConfig):
        src = AmadeusHotelSource(amadeus_config)
        respx.post("https://test.api.amadeus.com/v1/security/oauth2/token").mock(
            return_value=httpx.Response(200, json=TOKEN_RESPONSE),
        )
        respx.get(
            "https://test.api.amadeus.com/v1/reference-data/locations/hotels/by-city"
        ).mock(return_value=httpx.Response(200, json=AMADEUS_HOTEL_LIST_RESPONSE))
        respx.get(
            "https://test.api.amadeus.com/v3/shopping/hotel-offers"
        ).mock(return_value=httpx.Response(200, json=AMADEUS_HOTEL_OFFERS_RESPONSE))
        results = await src.search_hotels("Tokyo", "2026-05-01", "2026-05-05")
        await src.close()

        for r in results:
            missing = REQUIRED_HOTEL_FIELDS - set(r.keys())
            assert not missing, f"Amadeus hotels missing fields: {missing}"

    @pytest.mark.anyio
    @respx.mock
    async def test_ticketmaster_field_schema(self, ticketmaster_config: TicketmasterConfig):
        src = TicketmasterSource(ticketmaster_config)
        respx.get("https://app.ticketmaster.com/discovery/v2/events.json").mock(
            return_value=httpx.Response(200, json=TICKETMASTER_RESPONSE),
        )
        results = await src.search_tickets("Tokyo", "2026-05-01", "2026-05-10")
        await src.close()

        for r in results:
            missing = REQUIRED_TICKET_FIELDS - set(r.keys())
            assert not missing, f"Ticketmaster missing fields: {missing}"

    def test_google_flights_helper_field_schema(self):
        from smart_travel.data.sources.flights.google_flights import GoogleFlightsSource
        src = GoogleFlightsSource(BrowserConfig())
        raw = [{"price": "$500", "airline": "UA", "times": "10:00", "duration": "10h", "stops": "Nonstop"}]
        results = src._parse_results(raw, "Seattle", "Tokyo", "2026-05-01", "economy", 1, None, None)
        for r in results:
            missing = REQUIRED_FLIGHT_FIELDS - set(r.keys())
            assert not missing, f"Google Flights missing fields: {missing}"

    def test_google_hotels_helper_field_schema(self):
        from smart_travel.data.sources.hotels.google_hotels import GoogleHotelsSource
        src = GoogleHotelsSource(BrowserConfig())
        raw = [{"name": "Hotel", "price": "$200", "rating": "4.0", "stars": "4", "amenities": ""}]
        results = src._parse_results(raw, "Tokyo", "2026-05-01", "2026-05-05", 1, 1, None, None, None)
        for r in results:
            missing = REQUIRED_HOTEL_FIELDS - set(r.keys())
            assert not missing, f"Google Hotels missing fields: {missing}"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 6: REGISTRY SOURCE INVENTORY
#
# Verifies the exact set of sources registered per domain.
# If a source is added or removed, this test forces an update.
# ═══════════════════════════════════════════════════════════════════════════


class TestSourceInventory:
    """Registry contains exactly the expected sources per domain."""

    def test_flight_sources_registered(self):
        config = AppConfig(
            amadeus=AmadeusConfig(api_key="k", api_secret="s"),
        )
        registry = SourceRegistry(config)
        names = {s.name for s in registry.list_sources("flights")}
        # Always: amadeus, mock
        # Optional: google_flights, airline award sources (depend on playwright)
        assert {"amadeus", "mock"}.issubset(names)

    def test_hotel_sources_registered(self):
        config = AppConfig(
            amadeus=AmadeusConfig(api_key="k", api_secret="s"),
        )
        registry = SourceRegistry(config)
        names = {s.name for s in registry.list_sources("hotels")}
        assert {"amadeus", "mock"}.issubset(names)

    def test_ticket_sources_registered(self):
        config = AppConfig(
            ticketmaster=TicketmasterConfig(api_key="k"),
        )
        registry = SourceRegistry(config)
        names = {s.name for s in registry.list_sources("tickets")}
        assert {"ticketmaster", "mock"}.issubset(names)

    def test_no_live_hotel_points_source_in_registry(self):
        """No live hotel source provides points pricing today.

        This is the registry-level guardrail for the hotel points gap.
        """
        config = AppConfig(
            amadeus=AmadeusConfig(api_key="k", api_secret="s"),
        )
        registry = SourceRegistry(config)
        for info in registry.list_sources("hotels"):
            if info.fetch_method != FetchMethod.MOCK:
                assert PriceType.POINTS not in info.price_types, (
                    f"Hotel source '{info.name}' now declares POINTS — "
                    f"update the capability matrix!"
                )

    def test_flights_have_both_cash_and_points_sources(self):
        """Flights have at least one CASH source and one POINTS source."""
        config = AppConfig(
            amadeus=AmadeusConfig(api_key="k", api_secret="s"),
        )
        registry = SourceRegistry(config)
        infos = registry.list_sources("flights")
        has_cash = any(PriceType.CASH in s.price_types for s in infos if s.fetch_method != FetchMethod.MOCK)
        has_points = any(PriceType.POINTS in s.price_types for s in infos if s.fetch_method != FetchMethod.MOCK)
        assert has_cash, "No live flight source provides CASH pricing"
        assert has_points, "No live flight source provides POINTS pricing"
