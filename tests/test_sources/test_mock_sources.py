"""Tests for mock source wrappers."""

from __future__ import annotations

import pytest

from smart_travel.data.sources.flights.mock import MockFlightSource
from smart_travel.data.sources.hotels.mock import MockHotelSource
from smart_travel.data.sources.tickets.mock import MockTicketSource
from smart_travel.data.sources.base import FetchMethod, PriceType


class TestMockFlightSource:

    @pytest.mark.anyio
    async def test_always_available(self):
        src = MockFlightSource()
        assert await src.is_available()

    @pytest.mark.anyio
    async def test_returns_results(self):
        src = MockFlightSource()
        results = await src.search_flights("Seattle", "Tokyo", "2026-05-01")
        assert len(results) > 0

    @pytest.mark.anyio
    async def test_results_tagged_with_source(self):
        src = MockFlightSource()
        results = await src.search_flights("Seattle", "Tokyo", "2026-05-01")
        for r in results:
            assert r.get("source") == "mock"

    def test_info(self):
        src = MockFlightSource()
        assert src.info.name == "mock"
        assert src.info.domain == "flights"
        assert src.info.fetch_method == FetchMethod.MOCK
        assert src.info.priority == 999

    def test_info_includes_points_price_type(self):
        src = MockFlightSource()
        assert PriceType.CASH in src.info.price_types
        assert PriceType.POINTS in src.info.price_types

    @pytest.mark.anyio
    async def test_max_price_filter(self):
        src = MockFlightSource()
        results = await src.search_flights(
            "Seattle", "Tokyo", "2026-05-01", max_price=500.0,
        )
        for r in results:
            assert r["price_usd"] <= 500.0

    @pytest.mark.anyio
    async def test_round_trip(self):
        src = MockFlightSource()
        results = await src.search_flights(
            "Seattle", "Tokyo", "2026-05-01", return_date="2026-05-10",
        )
        assert len(results) == 1
        assert results[0]["type"] == "round_trip"
        for f in results[0]["outbound"]:
            assert f.get("source") == "mock"
        for f in results[0]["return"]:
            assert f.get("source") == "mock"


class TestMockHotelSource:

    @pytest.mark.anyio
    async def test_always_available(self):
        src = MockHotelSource()
        assert await src.is_available()

    @pytest.mark.anyio
    async def test_returns_results(self):
        src = MockHotelSource()
        results = await src.search_hotels("Tokyo", "2026-05-01", "2026-05-05")
        assert len(results) > 0

    @pytest.mark.anyio
    async def test_results_tagged_with_source(self):
        src = MockHotelSource()
        results = await src.search_hotels("Tokyo", "2026-05-01", "2026-05-05")
        for r in results:
            assert r.get("source") == "mock"

    def test_info(self):
        src = MockHotelSource()
        assert src.info.name == "mock"
        assert src.info.domain == "hotels"
        assert src.info.fetch_method == FetchMethod.MOCK

    def test_info_includes_points_price_type(self):
        src = MockHotelSource()
        assert PriceType.CASH in src.info.price_types
        assert PriceType.POINTS in src.info.price_types


class TestMockTicketSource:

    @pytest.mark.anyio
    async def test_always_available(self):
        src = MockTicketSource()
        assert await src.is_available()

    @pytest.mark.anyio
    async def test_returns_results(self):
        src = MockTicketSource()
        results = await src.search_tickets("Tokyo", "2026-05-01", "2026-05-10")
        assert len(results) > 0

    @pytest.mark.anyio
    async def test_results_tagged_with_source(self):
        src = MockTicketSource()
        results = await src.search_tickets("Tokyo", "2026-05-01", "2026-05-10")
        for r in results:
            assert r.get("source") == "mock"

    def test_info(self):
        src = MockTicketSource()
        assert src.info.name == "mock"
        assert src.info.domain == "tickets"
        assert src.info.fetch_method == FetchMethod.MOCK
