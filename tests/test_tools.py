"""Unit tests for travel search tool functions."""

from __future__ import annotations

import pytest

from smart_travel.data.mock_flights import search_flights
from smart_travel.data.mock_hotels import search_hotels
from smart_travel.data.mock_tickets import search_tickets


# ── Flight search tests ──────────────────────────────────────────────


class TestFlightSearch:
    """Tests for the flight search mock data layer."""

    def test_basic_search_returns_results(self):
        results = search_flights("Seattle", "Tokyo", "2026-05-01", seed=42)
        assert len(results) > 0

    def test_results_have_required_fields(self):
        results = search_flights("Seattle", "Tokyo", "2026-05-01", seed=42)
        required_fields = [
            "flight_number", "airline", "origin", "destination",
            "date", "departure_time", "duration", "stops",
            "cabin_class", "price_usd",
        ]
        for flight in results:
            for field in required_fields:
                assert field in flight, f"Missing field: {field}"

    def test_max_price_filter(self):
        results = search_flights(
            "Seattle", "Tokyo", "2026-05-01", max_price=500.0, seed=42
        )
        for flight in results:
            assert flight["price_usd"] <= 500.0

    def test_max_stops_filter(self):
        results = search_flights(
            "Seattle", "Tokyo", "2026-05-01", max_stops=0, seed=42
        )
        for flight in results:
            assert flight["stops"] == 0

    def test_cabin_class(self):
        economy = search_flights(
            "Seattle", "Tokyo", "2026-05-01", cabin_class="economy", seed=42
        )
        business = search_flights(
            "Seattle", "Tokyo", "2026-05-01", cabin_class="business", seed=42
        )
        # Business class should generally be more expensive
        avg_economy = sum(f["price_usd"] for f in economy) / len(economy)
        avg_business = sum(f["price_usd"] for f in business) / len(business)
        assert avg_business > avg_economy

    def test_passengers_multiplier(self):
        results = search_flights(
            "Seattle", "Tokyo", "2026-05-01", passengers=3, seed=42
        )
        for flight in results:
            assert flight["total_price_usd"] == pytest.approx(
                flight["price_usd"] * 3, rel=1e-2
            )

    def test_round_trip(self):
        results = search_flights(
            "Seattle", "Tokyo", "2026-05-01",
            return_date="2026-05-10", seed=42
        )
        assert len(results) == 1
        assert results[0]["type"] == "round_trip"
        assert "outbound" in results[0]
        assert "return" in results[0]
        assert len(results[0]["outbound"]) > 0
        assert len(results[0]["return"]) > 0

    def test_results_sorted_by_price(self):
        results = search_flights("New York", "London", "2026-06-15", seed=42)
        prices = [f["price_usd"] for f in results]
        assert prices == sorted(prices)

    def test_seed_reproducibility(self):
        r1 = search_flights("Seattle", "Tokyo", "2026-05-01", seed=42)
        r2 = search_flights("Seattle", "Tokyo", "2026-05-01", seed=42)
        assert r1 == r2

    def test_no_results_with_impossible_filter(self):
        results = search_flights(
            "Seattle", "Tokyo", "2026-05-01", max_price=1.0, seed=42
        )
        assert len(results) == 0


# ── Hotel search tests ───────────────────────────────────────────────


class TestHotelSearch:
    """Tests for the hotel search mock data layer."""

    def test_basic_search_returns_results(self):
        results = search_hotels("Tokyo", "2026-05-01", "2026-05-05", seed=42)
        assert len(results) > 0

    def test_results_have_required_fields(self):
        results = search_hotels("Tokyo", "2026-05-01", "2026-05-05", seed=42)
        required_fields = [
            "name", "city", "star_rating", "guest_rating",
            "price_per_night_usd", "amenities", "check_in", "check_out",
        ]
        for hotel in results:
            for field in required_fields:
                assert field in hotel, f"Missing field: {field}"

    def test_min_stars_filter(self):
        results = search_hotels(
            "Tokyo", "2026-05-01", "2026-05-05", min_stars=4, seed=42
        )
        for hotel in results:
            assert hotel["star_rating"] >= 4

    def test_max_price_filter(self):
        results = search_hotels(
            "Tokyo", "2026-05-01", "2026-05-05",
            max_price_per_night=100.0, seed=42
        )
        for hotel in results:
            assert hotel["price_per_night_usd"] <= 100.0

    def test_required_amenities_filter(self):
        results = search_hotels(
            "Tokyo", "2026-05-01", "2026-05-05",
            required_amenities=["pool", "wifi"], seed=42
        )
        for hotel in results:
            assert "pool" in hotel["amenities"]
            assert "wifi" in hotel["amenities"]

    def test_total_price_calculation(self):
        results = search_hotels(
            "Tokyo", "2026-05-01", "2026-05-05", rooms=2, seed=42
        )
        for hotel in results:
            expected = hotel["price_per_night_usd"] * 4 * 2  # 4 nights, 2 rooms
            assert hotel["total_price_usd"] == pytest.approx(expected, rel=1e-2)

    def test_results_sorted_by_price(self):
        results = search_hotels("Paris", "2026-06-01", "2026-06-05", seed=42)
        prices = [h["price_per_night_usd"] for h in results]
        assert prices == sorted(prices)

    def test_seed_reproducibility(self):
        r1 = search_hotels("Tokyo", "2026-05-01", "2026-05-05", seed=42)
        r2 = search_hotels("Tokyo", "2026-05-01", "2026-05-05", seed=42)
        assert r1 == r2


# ── Ticket search tests ─────────────────────────────────────────────


class TestTicketSearch:
    """Tests for the ticket/event search mock data layer."""

    def test_basic_search_returns_results(self):
        results = search_tickets("Tokyo", "2026-05-01", "2026-05-10", seed=42)
        assert len(results) > 0

    def test_results_have_required_fields(self):
        results = search_tickets("Tokyo", "2026-05-01", "2026-05-10", seed=42)
        required_fields = [
            "name", "event_type", "venue", "city", "date", "time",
            "price_range_usd", "average_price_usd", "tickets_available",
        ]
        for event in required_fields:
            pass  # checked below
        for event in results:
            for field in required_fields:
                assert field in event, f"Missing field: {field}"

    def test_event_type_filter(self):
        results = search_tickets(
            "Tokyo", "2026-05-01", "2026-05-10",
            event_type="concert", seed=42
        )
        for event in results:
            assert event["event_type"] == "concert"

    def test_max_price_filter(self):
        results = search_tickets(
            "Tokyo", "2026-05-01", "2026-05-10",
            max_price=50.0, seed=42
        )
        for event in results:
            assert event["average_price_usd"] <= 50.0

    def test_min_rating_filter(self):
        results = search_tickets(
            "Tokyo", "2026-05-01", "2026-05-10",
            min_rating=4.5, seed=42
        )
        for event in results:
            assert event["rating"] >= 4.5

    def test_all_event_types_returned_when_no_filter(self):
        results = search_tickets("New York", "2026-05-01", "2026-05-15", seed=42)
        event_types = {e["event_type"] for e in results}
        # Should have at least 2 different types
        assert len(event_types) >= 2

    def test_results_sorted_by_date(self):
        results = search_tickets("London", "2026-06-01", "2026-06-15", seed=42)
        dates = [(e["date"], e["time"]) for e in results]
        assert dates == sorted(dates)

    def test_seed_reproducibility(self):
        r1 = search_tickets("Tokyo", "2026-05-01", "2026-05-10", seed=42)
        r2 = search_tickets("Tokyo", "2026-05-01", "2026-05-10", seed=42)
        assert r1 == r2

    def test_price_range_consistency(self):
        results = search_tickets("Tokyo", "2026-05-01", "2026-05-10", seed=42)
        for event in results:
            assert event["price_range_usd"]["min"] <= event["price_range_usd"]["max"]
            avg = event["average_price_usd"]
            assert event["price_range_usd"]["min"] <= avg <= event["price_range_usd"]["max"]
