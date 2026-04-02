"""Tests for the resolver (high-level search orchestration)."""

from __future__ import annotations

import pytest

from smart_travel.config import AppConfig
from smart_travel.data.resolver import (
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
