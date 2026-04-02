"""Tests for browser-based data sources (Google Flights, Google Hotels)."""

from __future__ import annotations

import pytest

from smart_travel.config import BrowserConfig


class TestGoogleFlightsSource:
    """Tests for the Google Flights browser source."""

    def test_import(self):
        from smart_travel.data.sources.flights.google_flights import GoogleFlightsSource
        assert GoogleFlightsSource is not None

    def test_source_info(self):
        from smart_travel.data.sources.flights.google_flights import GoogleFlightsSource
        from smart_travel.data.sources.base import FetchMethod, PriceType

        source = GoogleFlightsSource(BrowserConfig())
        assert source.info.name == "google_flights"
        assert source.info.domain == "flights"
        assert source.info.fetch_method == FetchMethod.BROWSER
        assert PriceType.CASH in source.info.price_types
        assert source.info.priority == 20

    @pytest.mark.anyio
    async def test_is_available_depends_on_playwright(self):
        """is_available returns True/False based on playwright import."""
        from smart_travel.data.sources.flights.google_flights import GoogleFlightsSource
        source = GoogleFlightsSource(BrowserConfig())
        result = await source.is_available()
        # Result depends on whether playwright is installed in test env
        assert isinstance(result, bool)

    def test_build_url(self):
        from smart_travel.data.sources.flights.google_flights import GoogleFlightsSource
        source = GoogleFlightsSource(BrowserConfig())
        url = source._build_url("SEA", "NRT", "2026-05-01", None, "economy")
        assert "google.com/travel/flights" in url
        assert "SEA" in url
        assert "NRT" in url

    def test_parse_results_filters_max_price(self):
        from smart_travel.data.sources.flights.google_flights import GoogleFlightsSource
        source = GoogleFlightsSource(BrowserConfig())
        raw = [
            {"price": "$500", "airline": "UA", "times": "10:00", "duration": "10h", "stops": "Nonstop"},
            {"price": "$1200", "airline": "DL", "times": "14:00", "duration": "11h", "stops": "1 stop"},
        ]
        results = source._parse_results(
            raw, "Seattle", "Tokyo", "2026-05-01", "economy", 1, 800.0, None,
        )
        assert len(results) == 1
        assert results[0]["price_usd"] == 500.0

    def test_parse_results_filters_max_stops(self):
        from smart_travel.data.sources.flights.google_flights import GoogleFlightsSource
        source = GoogleFlightsSource(BrowserConfig())
        raw = [
            {"price": "$500", "airline": "UA", "times": "10:00", "duration": "10h", "stops": "Nonstop"},
            {"price": "$400", "airline": "DL", "times": "14:00", "duration": "15h", "stops": "2 stops"},
        ]
        results = source._parse_results(
            raw, "Seattle", "Tokyo", "2026-05-01", "economy", 1, None, 0,
        )
        assert len(results) == 1
        assert results[0]["stops"] == 0


class TestGoogleHotelsSource:
    """Tests for the Google Hotels browser source."""

    def test_import(self):
        from smart_travel.data.sources.hotels.google_hotels import GoogleHotelsSource
        assert GoogleHotelsSource is not None

    def test_source_info(self):
        from smart_travel.data.sources.hotels.google_hotels import GoogleHotelsSource
        from smart_travel.data.sources.base import FetchMethod, PriceType

        source = GoogleHotelsSource(BrowserConfig())
        assert source.info.name == "google_hotels"
        assert source.info.domain == "hotels"
        assert source.info.fetch_method == FetchMethod.BROWSER
        assert PriceType.CASH in source.info.price_types
        assert source.info.priority == 20

    def test_build_url(self):
        from smart_travel.data.sources.hotels.google_hotels import GoogleHotelsSource
        source = GoogleHotelsSource(BrowserConfig())
        url = source._build_url("Tokyo", "2026-05-01", "2026-05-05", 2)
        assert "google.com/travel/hotels" in url
        assert "Tokyo" in url

    def test_parse_results_filters_max_price(self):
        from smart_travel.data.sources.hotels.google_hotels import GoogleHotelsSource
        source = GoogleHotelsSource(BrowserConfig())
        raw = [
            {"name": "Budget Inn", "price": "$80", "rating": "3.5", "stars": "2", "amenities": "WiFi"},
            {"name": "Luxury Grand", "price": "$500", "rating": "4.8", "stars": "5", "amenities": "WiFi, Pool"},
        ]
        results = source._parse_results(
            raw, "Tokyo", "2026-05-01", "2026-05-05", 1, 1,
            None, 200.0, None,
        )
        assert len(results) == 1
        assert results[0]["name"] == "Budget Inn"

    def test_parse_results_filters_min_stars(self):
        from smart_travel.data.sources.hotels.google_hotels import GoogleHotelsSource
        source = GoogleHotelsSource(BrowserConfig())
        raw = [
            {"name": "Budget Inn", "price": "$80", "rating": "3.5", "stars": "2", "amenities": "WiFi"},
            {"name": "Nice Hotel", "price": "$200", "rating": "4.2", "stars": "4", "amenities": "WiFi, Pool"},
        ]
        results = source._parse_results(
            raw, "Tokyo", "2026-05-01", "2026-05-05", 1, 1,
            4, None, None,
        )
        assert len(results) == 1
        assert results[0]["name"] == "Nice Hotel"

    def test_parse_results_calculates_total_price(self):
        from smart_travel.data.sources.hotels.google_hotels import GoogleHotelsSource
        source = GoogleHotelsSource(BrowserConfig())
        raw = [
            {"name": "Hotel", "price": "$100", "rating": "4.0", "stars": "3", "amenities": ""},
        ]
        results = source._parse_results(
            raw, "Tokyo", "2026-05-01", "2026-05-04", 1, 1,
            None, None, None,
        )
        assert len(results) == 1
        # 3 nights * $100 = $300
        assert results[0]["total_nights"] == 3
        assert results[0]["total_price_usd"] == 300.0
