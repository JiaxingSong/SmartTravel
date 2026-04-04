"""Tests for the source registry."""

from __future__ import annotations

import pytest

from smart_travel.config import AppConfig
from smart_travel.data.sources.base import FetchMethod, PriceType, SourceInfo
from smart_travel.data.sources.registry import SourceRegistry


class TestRegistration:

    def test_builtin_sources_registered(self, full_config: AppConfig):
        reg = SourceRegistry(full_config)
        infos = reg.list_sources()
        names = {i.name for i in infos}
        # At minimum, expect mock + live for each domain
        assert "mock" in names
        assert "amadeus" in names

    def test_list_sources_by_domain(self, full_config: AppConfig):
        reg = SourceRegistry(full_config)
        flight_infos = reg.list_sources(domain="flights")
        assert all(i.domain == "flights" for i in flight_infos)
        hotel_infos = reg.list_sources(domain="hotels")
        assert all(i.domain == "hotels" for i in hotel_infos)
        ticket_infos = reg.list_sources(domain="tickets")
        assert all(i.domain == "tickets" for i in ticket_infos)

    def test_register_custom_source(self, full_config: AppConfig):
        """A V2-style source can be registered dynamically."""
        reg = SourceRegistry(full_config)

        from smart_travel.data.sources.flights.mock import MockFlightSource
        extra = MockFlightSource()
        # Mutate info for test distinction (SourceInfo is frozen, so create new)
        extra.info = SourceInfo(
            name="custom_test",
            domain="flights",
            fetch_method=FetchMethod.MOCK,
            price_types=frozenset({PriceType.CASH}),
            priority=500,
        )
        reg.register(extra)

        names = {i.name for i in reg.list_sources("flights")}
        assert "custom_test" in names


class TestGetAvailable:

    @pytest.mark.anyio
    async def test_excludes_unconfigured(self, no_keys_config: AppConfig):
        reg = SourceRegistry(no_keys_config)
        available = await reg.get_available("flights")
        names = [s.info.name for s in available]
        # Amadeus should be excluded (no keys)
        assert "amadeus" not in names
        # Mock is always available
        assert "mock" in names

    @pytest.mark.anyio
    async def test_filter_by_source_name(self, full_config: AppConfig):
        reg = SourceRegistry(full_config)
        available = await reg.get_available("flights", source_names=["amadeus"])
        assert all(s.info.name == "amadeus" for s in available)

    @pytest.mark.anyio
    async def test_filter_by_price_type(self, full_config: AppConfig):
        reg = SourceRegistry(full_config)
        available = await reg.get_available(
            "flights", price_types={PriceType.POINTS},
        )
        for s in available:
            assert PriceType.POINTS in s.info.price_types

    @pytest.mark.anyio
    async def test_sorted_by_priority(self, no_keys_config: AppConfig):
        reg = SourceRegistry(no_keys_config)
        available = await reg.get_available("flights")
        priorities = [s.info.priority for s in available]
        assert priorities == sorted(priorities)

    @pytest.mark.anyio
    async def test_airline_filter_passes_aggregators(self, full_config: AppConfig):
        """Sources with empty airlines set (aggregators) still match any airline filter."""
        reg = SourceRegistry(full_config)
        available = await reg.get_available("flights", airlines=["DL"])
        # Amadeus has empty airlines → matches everything
        names = [s.info.name for s in available]
        assert "amadeus" in names


class TestCloseAll:

    @pytest.mark.anyio
    async def test_close_all_does_not_raise(self, no_keys_config: AppConfig):
        reg = SourceRegistry(no_keys_config)
        await reg.close_all()  # should not raise
