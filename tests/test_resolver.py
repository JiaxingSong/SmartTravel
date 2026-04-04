"""Tests for the resolver (high-level search orchestration)."""

from __future__ import annotations

import pytest

from smart_travel.config import AppConfig
from smart_travel.data.resolver import (
    _merge_hotel_results,
    search_flights,
    search_hotels,
    search_tickets,
    set_registry,
    set_cache,
)
from smart_travel.data.sources.registry import SourceRegistry


@pytest.fixture(autouse=True)
def _reset_resolver():
    """Ensure the module-level registry and cache are cleared between tests."""
    set_registry(None)  # type: ignore[arg-type]
    set_cache(None)  # type: ignore[arg-type]
    yield
    set_registry(None)  # type: ignore[arg-type]
    set_cache(None)  # type: ignore[arg-type]


class TestFlightResolver:

    @pytest.mark.anyio
    async def test_mock_fallback(self, no_keys_config: AppConfig):
        """With no API keys, resolver falls back to mock data."""
        set_registry(SourceRegistry(no_keys_config))
        results = await search_flights("Seattle", "Tokyo", "2026-05-01")
        assert len(results) > 0
        # All results should be tagged with source
        for r in results:
            assert r.get("source") == "mock"

    @pytest.mark.anyio
    async def test_source_filter(self, no_keys_config: AppConfig):
        """Filtering to only 'mock' should still work."""
        set_registry(SourceRegistry(no_keys_config))
        results = await search_flights(
            "Seattle", "Tokyo", "2026-05-01", sources=["mock"],
        )
        assert len(results) > 0

    @pytest.mark.anyio
    async def test_source_filter_nonexistent(self, no_keys_config: AppConfig):
        """Filtering to a source that doesn't exist returns empty."""
        set_registry(SourceRegistry(no_keys_config))
        results = await search_flights(
            "Seattle", "Tokyo", "2026-05-01",
            sources=["nonexistent_source"],
        )
        assert results == []

    @pytest.mark.anyio
    async def test_round_trip_through_mock(self, no_keys_config: AppConfig):
        set_registry(SourceRegistry(no_keys_config))
        results = await search_flights(
            "Seattle", "Tokyo", "2026-05-01", return_date="2026-05-10",
        )
        assert len(results) == 1
        assert results[0].get("type") == "round_trip"

    @pytest.mark.anyio
    async def test_max_price_filter_with_mock(self, no_keys_config: AppConfig):
        set_registry(SourceRegistry(no_keys_config))
        results = await search_flights(
            "Seattle", "Tokyo", "2026-05-01", max_price=500.0,
        )
        for r in results:
            assert r["price_usd"] <= 500.0


class TestHotelResolver:

    @pytest.mark.anyio
    async def test_mock_fallback(self, no_keys_config: AppConfig):
        set_registry(SourceRegistry(no_keys_config))
        results = await search_hotels("Tokyo", "2026-05-01", "2026-05-05")
        assert len(results) > 0
        for r in results:
            assert r.get("source") == "mock"

    @pytest.mark.anyio
    async def test_min_stars(self, no_keys_config: AppConfig):
        set_registry(SourceRegistry(no_keys_config))
        results = await search_hotels(
            "Tokyo", "2026-05-01", "2026-05-05", min_stars=4,
        )
        for r in results:
            assert r["star_rating"] >= 4

    @pytest.mark.anyio
    async def test_hotel_results_include_points(self, no_keys_config: AppConfig):
        """Resolver returns hotels with points pricing from mock."""
        set_registry(SourceRegistry(no_keys_config))
        results = await search_hotels("Tokyo", "2026-05-01", "2026-05-05")
        has_points = [r for r in results if r.get("points_price") is not None]
        assert len(has_points) > 0
        for r in has_points:
            assert isinstance(r["points_price"], int)
            assert r["points_price"] > 0
            assert isinstance(r["points_program"], str)


class TestHotelMerge:
    """Tests for _merge_hotel_results()."""

    def test_cash_only_passthrough(self):
        """Cash-only results pass through unchanged (sorted by price)."""
        results = [
            {"name": "Hotel B", "city": "Tokyo", "check_in": "2026-05-01",
             "price_per_night_usd": 200.0, "points_price": None, "points_program": None},
            {"name": "Hotel A", "city": "Tokyo", "check_in": "2026-05-01",
             "price_per_night_usd": 100.0, "points_price": None, "points_program": None},
        ]
        merged = _merge_hotel_results(results)
        assert len(merged) == 2
        assert merged[0]["price_per_night_usd"] == 100.0
        assert merged[1]["price_per_night_usd"] == 200.0

    def test_merge_cash_and_points(self):
        """Points-only result merges into matching cash result."""
        cash = {
            "name": "Marriott Tokyo", "city": "Tokyo", "check_in": "2026-05-01",
            "price_per_night_usd": 200.0, "points_price": None, "points_program": None,
        }
        points_only = {
            "name": "Marriott Tokyo", "city": "Tokyo", "check_in": "2026-05-01",
            "price_per_night_usd": None, "points_price": 25000, "points_program": "marriott bonvoy",
        }
        merged = _merge_hotel_results([cash, points_only])
        assert len(merged) == 1
        assert merged[0]["price_per_night_usd"] == 200.0
        assert merged[0]["points_price"] == 25000
        assert merged[0]["points_program"] == "marriott bonvoy"

    def test_unmatched_points_appended(self):
        """Unmatched points-only results are appended to output."""
        cash = {
            "name": "Hilton Tokyo", "city": "Tokyo", "check_in": "2026-05-01",
            "price_per_night_usd": 180.0, "points_price": None, "points_program": None,
        }
        points_only = {
            "name": "Marriott Tokyo", "city": "Tokyo", "check_in": "2026-05-01",
            "price_per_night_usd": None, "points_price": 25000, "points_program": "marriott bonvoy",
        }
        merged = _merge_hotel_results([cash, points_only])
        assert len(merged) == 2
        names = {r["name"] for r in merged}
        assert "Hilton Tokyo" in names
        assert "Marriott Tokyo" in names


class TestTicketResolver:

    @pytest.mark.anyio
    async def test_mock_fallback(self, no_keys_config: AppConfig):
        set_registry(SourceRegistry(no_keys_config))
        results = await search_tickets("Tokyo", "2026-05-01", "2026-05-10")
        assert len(results) > 0
        for r in results:
            assert r.get("source") == "mock"

    @pytest.mark.anyio
    async def test_event_type_filter(self, no_keys_config: AppConfig):
        set_registry(SourceRegistry(no_keys_config))
        results = await search_tickets(
            "Tokyo", "2026-05-01", "2026-05-10", event_type="concert",
        )
        for r in results:
            assert r["event_type"] == "concert"
