"""Tests for airline award browser-based data sources.

Tests UnitedAwardSource, DeltaAwardSource, AmericanAwardSource, and
AlaskaAwardSource — all Playwright-based scrapers that return points/miles
prices from airline award search pages.
"""

from __future__ import annotations

import pytest

from smart_travel.config import BrowserConfig


# =====================================================================
# United Airlines Award Source
# =====================================================================

class TestUnitedAwardSource:
    """Tests for the United Airlines award browser source."""

    def test_import(self):
        from smart_travel.data.sources.flights.united import UnitedAwardSource
        assert UnitedAwardSource is not None

    def test_source_info(self):
        from smart_travel.data.sources.flights.united import UnitedAwardSource
        from smart_travel.data.sources.base import FetchMethod, PriceType

        source = UnitedAwardSource(BrowserConfig())
        assert source.info.name == "united_award"
        assert source.info.domain == "flights"
        assert source.info.fetch_method == FetchMethod.BROWSER
        assert PriceType.POINTS in source.info.price_types
        assert source.info.priority == 20

    @pytest.mark.anyio
    async def test_is_available_depends_on_playwright(self):
        """is_available returns True/False based on playwright import."""
        from smart_travel.data.sources.flights.united import UnitedAwardSource
        source = UnitedAwardSource(BrowserConfig())
        result = await source.is_available()
        assert isinstance(result, bool)

    def test_build_url(self):
        from smart_travel.data.sources.flights.united import UnitedAwardSource
        source = UnitedAwardSource(BrowserConfig())
        url = source._build_url("SEA", "NRT", "2026-05-01", "economy")
        assert "united.com" in url
        assert "SEA" in url
        assert "NRT" in url
        assert "at=1" in url  # Award travel flag
        assert "sc=7" in url  # Economy cabin code

    def test_parse_results_extracts_points(self):
        from smart_travel.data.sources.flights.united import UnitedAwardSource
        source = UnitedAwardSource(BrowserConfig())
        raw = [
            {
                "miles": "75,000 miles",
                "airline": "United Airlines",
                "flightNum": "UA876",
                "times": "10:30 AM",
                "duration": "11h 15m",
                "stops": "Nonstop",
            },
            {
                "miles": "55,000 miles",
                "airline": "United Airlines",
                "flightNum": "UA234",
                "times": "2:15 PM",
                "duration": "13h 30m",
                "stops": "1 stop",
            },
        ]
        results = source._parse_results(
            raw, "Seattle", "Tokyo", "2026-05-01", "economy", 1, None,
        )
        assert len(results) == 2
        # Results sorted by points ascending
        assert results[0]["points_price"] == 55000
        assert results[1]["points_price"] == 75000
        assert results[0]["points_program"] == "united"
        assert results[0]["price_usd"] is None
        assert results[0]["source"] == "united_award"
        assert results[0]["stops"] == 1
        assert results[1]["stops"] == 0

    def test_parse_results_skips_zero_miles(self):
        from smart_travel.data.sources.flights.united import UnitedAwardSource
        source = UnitedAwardSource(BrowserConfig())
        raw = [
            {"miles": "0 miles", "airline": "UA", "flightNum": "", "times": "", "duration": "", "stops": ""},
            {"miles": "", "airline": "UA", "flightNum": "", "times": "", "duration": "", "stops": ""},
            {"miles": "75,000 miles", "airline": "UA", "flightNum": "UA876", "times": "10:30", "duration": "11h", "stops": "Nonstop"},
        ]
        results = source._parse_results(
            raw, "Seattle", "Tokyo", "2026-05-01", "economy", 1, None,
        )
        assert len(results) == 1
        assert results[0]["points_price"] == 75000


# =====================================================================
# Delta Air Lines Award Source
# =====================================================================

class TestDeltaAwardSource:
    """Tests for the Delta Air Lines award browser source."""

    def test_import(self):
        from smart_travel.data.sources.flights.delta import DeltaAwardSource
        assert DeltaAwardSource is not None

    def test_source_info(self):
        from smart_travel.data.sources.flights.delta import DeltaAwardSource
        from smart_travel.data.sources.base import FetchMethod, PriceType

        source = DeltaAwardSource(BrowserConfig())
        assert source.info.name == "delta_award"
        assert source.info.domain == "flights"
        assert source.info.fetch_method == FetchMethod.BROWSER
        assert PriceType.POINTS in source.info.price_types
        assert source.info.priority == 20

    @pytest.mark.anyio
    async def test_is_available_depends_on_playwright(self):
        """is_available returns True/False based on playwright import."""
        from smart_travel.data.sources.flights.delta import DeltaAwardSource
        source = DeltaAwardSource(BrowserConfig())
        result = await source.is_available()
        assert isinstance(result, bool)

    def test_build_url(self):
        from smart_travel.data.sources.flights.delta import DeltaAwardSource
        source = DeltaAwardSource(BrowserConfig())
        url = source._build_url("SEA", "NRT", "2026-05-01", "business")
        assert "delta.com" in url
        assert "SEA" in url
        assert "NRT" in url
        assert "awardTravel=true" in url
        assert "DELTA_ONE" in url  # Business cabin code

    def test_parse_results_extracts_points(self):
        from smart_travel.data.sources.flights.delta import DeltaAwardSource
        source = DeltaAwardSource(BrowserConfig())
        raw = [
            {
                "miles": "70,000 miles",
                "airline": "Delta Air Lines",
                "flightNum": "DL167",
                "times": "11:45 AM",
                "duration": "12h 00m",
                "stops": "Nonstop",
            },
            {
                "miles": "45,000 miles",
                "airline": "Delta Air Lines",
                "flightNum": "DL890",
                "times": "3:00 PM",
                "duration": "14h 20m",
                "stops": "1 stop",
            },
        ]
        results = source._parse_results(
            raw, "Seattle", "Tokyo", "2026-05-01", "economy", 1, None,
        )
        assert len(results) == 2
        # Sorted by points ascending
        assert results[0]["points_price"] == 45000
        assert results[1]["points_price"] == 70000
        assert results[0]["points_program"] == "delta"
        assert results[0]["price_usd"] is None
        assert results[0]["source"] == "delta_award"

    def test_parse_results_skips_zero_miles(self):
        from smart_travel.data.sources.flights.delta import DeltaAwardSource
        source = DeltaAwardSource(BrowserConfig())
        raw = [
            {"miles": "0", "airline": "DL", "flightNum": "", "times": "", "duration": "", "stops": ""},
            {"miles": "no miles", "airline": "DL", "flightNum": "", "times": "", "duration": "", "stops": ""},
            {"miles": "70,000 miles", "airline": "DL", "flightNum": "DL167", "times": "11:45", "duration": "12h", "stops": "Nonstop"},
        ]
        results = source._parse_results(
            raw, "Seattle", "Tokyo", "2026-05-01", "economy", 1, None,
        )
        assert len(results) == 1
        assert results[0]["points_price"] == 70000


# =====================================================================
# American Airlines Award Source
# =====================================================================

class TestAmericanAwardSource:
    """Tests for the American Airlines award browser source."""

    def test_import(self):
        from smart_travel.data.sources.flights.american import AmericanAwardSource
        assert AmericanAwardSource is not None

    def test_source_info(self):
        from smart_travel.data.sources.flights.american import AmericanAwardSource
        from smart_travel.data.sources.base import FetchMethod, PriceType

        source = AmericanAwardSource(BrowserConfig())
        assert source.info.name == "american_award"
        assert source.info.domain == "flights"
        assert source.info.fetch_method == FetchMethod.BROWSER
        assert PriceType.POINTS in source.info.price_types
        assert source.info.priority == 20

    @pytest.mark.anyio
    async def test_is_available_depends_on_playwright(self):
        """is_available returns True/False based on playwright import."""
        from smart_travel.data.sources.flights.american import AmericanAwardSource
        source = AmericanAwardSource(BrowserConfig())
        result = await source.is_available()
        assert isinstance(result, bool)

    def test_build_url(self):
        from smart_travel.data.sources.flights.american import AmericanAwardSource
        source = AmericanAwardSource(BrowserConfig())
        url = source._build_url("SEA", "NRT", "2026-05-01", "first")
        assert "aa.com" in url
        assert "SEA" in url
        assert "NRT" in url
        assert "bookingType=award" in url
        assert "cabinType=first" in url

    def test_parse_results_extracts_points(self):
        from smart_travel.data.sources.flights.american import AmericanAwardSource
        source = AmericanAwardSource(BrowserConfig())
        raw = [
            {
                "miles": "60,000 miles",
                "airline": "American Airlines",
                "flightNum": "AA123",
                "times": "9:00 AM",
                "duration": "12h 30m",
                "stops": "Nonstop",
            },
            {
                "miles": "40,000 miles",
                "airline": "American Airlines",
                "flightNum": "AA456",
                "times": "1:30 PM",
                "duration": "15h 00m",
                "stops": "2 stops",
            },
        ]
        results = source._parse_results(
            raw, "Seattle", "Tokyo", "2026-05-01", "economy", 1, None,
        )
        assert len(results) == 2
        # Sorted by points ascending
        assert results[0]["points_price"] == 40000
        assert results[1]["points_price"] == 60000
        assert results[0]["points_program"] == "american"
        assert results[0]["price_usd"] is None
        assert results[0]["source"] == "american_award"
        assert results[0]["stops"] == 2
        assert results[1]["stops"] == 0

    def test_parse_results_skips_zero_miles(self):
        from smart_travel.data.sources.flights.american import AmericanAwardSource
        source = AmericanAwardSource(BrowserConfig())
        raw = [
            {"miles": "0 miles", "airline": "AA", "flightNum": "", "times": "", "duration": "", "stops": ""},
            {"miles": "", "airline": "AA", "flightNum": "", "times": "", "duration": "", "stops": ""},
            {"miles": "60,000 miles", "airline": "AA", "flightNum": "AA123", "times": "9:00", "duration": "12h", "stops": "Direct"},
        ]
        results = source._parse_results(
            raw, "Seattle", "Tokyo", "2026-05-01", "economy", 1, None,
        )
        assert len(results) == 1
        assert results[0]["points_price"] == 60000


# =====================================================================
# Alaska Airlines Award Source
# =====================================================================

class TestAlaskaAwardSource:
    """Tests for the Alaska Airlines award browser source."""

    def test_import(self):
        from smart_travel.data.sources.flights.alaska import AlaskaAwardSource
        assert AlaskaAwardSource is not None

    def test_source_info(self):
        from smart_travel.data.sources.flights.alaska import AlaskaAwardSource
        from smart_travel.data.sources.base import FetchMethod, PriceType

        source = AlaskaAwardSource(BrowserConfig())
        assert source.info.name == "alaska_award"
        assert source.info.domain == "flights"
        assert source.info.fetch_method == FetchMethod.BROWSER
        assert PriceType.POINTS in source.info.price_types
        assert source.info.priority == 20

    @pytest.mark.anyio
    async def test_is_available_depends_on_playwright(self):
        """is_available returns True/False based on playwright import."""
        from smart_travel.data.sources.flights.alaska import AlaskaAwardSource
        source = AlaskaAwardSource(BrowserConfig())
        result = await source.is_available()
        assert isinstance(result, bool)

    def test_build_url(self):
        from smart_travel.data.sources.flights.alaska import AlaskaAwardSource
        source = AlaskaAwardSource(BrowserConfig())
        url = source._build_url("SEA", "NRT", "2026-05-01", "first")
        assert "alaskaair.com" in url
        assert "SEA" in url
        assert "NRT" in url
        assert "awardBooking=true" in url
        assert "cabinClass=first" in url

    def test_parse_results_extracts_points(self):
        from smart_travel.data.sources.flights.alaska import AlaskaAwardSource
        source = AlaskaAwardSource(BrowserConfig())
        raw = [
            {
                "miles": "50,000 miles",
                "airline": "Alaska Airlines",
                "flightNum": "AS123",
                "times": "8:00 AM",
                "duration": "5h 30m",
                "stops": "Nonstop",
            },
            {
                "miles": "30,000 miles",
                "airline": "Alaska Airlines",
                "flightNum": "AS456",
                "times": "12:00 PM",
                "duration": "7h 00m",
                "stops": "1 stop",
            },
        ]
        results = source._parse_results(
            raw, "Seattle", "Los Angeles", "2026-05-01", "economy", 1, None,
        )
        assert len(results) == 2
        # Sorted by points ascending
        assert results[0]["points_price"] == 30000
        assert results[1]["points_price"] == 50000
        assert results[0]["points_program"] == "alaska"
        assert results[0]["price_usd"] is None
        assert results[0]["source"] == "alaska_award"
        assert results[0]["stops"] == 1
        assert results[1]["stops"] == 0

    def test_parse_results_skips_zero_miles(self):
        from smart_travel.data.sources.flights.alaska import AlaskaAwardSource
        source = AlaskaAwardSource(BrowserConfig())
        raw = [
            {"miles": "0", "airline": "AS", "flightNum": "", "times": "", "duration": "", "stops": ""},
            {"miles": "not available", "airline": "AS", "flightNum": "", "times": "", "duration": "", "stops": ""},
            {"miles": "50,000 miles", "airline": "AS", "flightNum": "AS123", "times": "8:00", "duration": "5h", "stops": "Nonstop"},
        ]
        results = source._parse_results(
            raw, "Seattle", "Los Angeles", "2026-05-01", "economy", 1, None,
        )
        assert len(results) == 1
        assert results[0]["points_price"] == 50000
