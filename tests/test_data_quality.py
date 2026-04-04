"""Tests for data quality transparency.

Covers:
- Mock results carry ``_data_quality == "mock"``
- Source status diagnostics
- Tool output contains mock warnings
- Dynamic system prompt reflects source availability
- ``_data_quality`` field present in JSON tool output
"""

from __future__ import annotations

import json

import pytest

from smart_travel.config import AppConfig, AmadeusConfig, TicketmasterConfig
from smart_travel.data.sources.registry import SourceRegistry, SourceStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_config(**overrides) -> AppConfig:
    """Return an AppConfig with optional per-source overrides."""
    return AppConfig(**overrides)


# ---------------------------------------------------------------------------
# TestMockResultsCarryDataQuality
# ---------------------------------------------------------------------------

class TestMockResultsCarryDataQuality:
    """Every mock-fallback result must carry ``_data_quality == "mock"``."""

    @pytest.mark.anyio
    async def test_flights_mock_data_quality(self):
        from smart_travel.data.resolver import search_flights

        results = await search_flights(
            origin="Seattle",
            destination="Tokyo",
            departure_date="2026-06-01",
        )
        assert len(results) > 0
        for r in results:
            assert r.get("_data_quality") == "mock", f"Missing _data_quality on {r}"

    @pytest.mark.anyio
    async def test_hotels_mock_data_quality(self):
        from smart_travel.data.resolver import search_hotels

        results = await search_hotels(
            city="Tokyo",
            check_in="2026-06-01",
            check_out="2026-06-05",
        )
        assert len(results) > 0
        for r in results:
            assert r.get("_data_quality") == "mock", f"Missing _data_quality on {r}"

    @pytest.mark.anyio
    async def test_tickets_mock_data_quality(self):
        from smart_travel.data.resolver import search_tickets

        results = await search_tickets(
            city="Tokyo",
            date_from="2026-06-01",
            date_to="2026-06-10",
        )
        assert len(results) > 0
        for r in results:
            assert r.get("_data_quality") == "mock", f"Missing _data_quality on {r}"


# ---------------------------------------------------------------------------
# TestSourceStatusDiagnostics
# ---------------------------------------------------------------------------

class TestSourceStatusDiagnostics:
    """SourceStatus correctly reflects configuration state."""

    @pytest.mark.anyio
    async def test_no_keys_all_mock(self):
        """With no API keys, only mock sources are available."""
        config = _default_config()
        registry = SourceRegistry(config)
        status = await registry.source_status()

        assert not status.any_live_available
        # At least one mock source must be available
        mock_entries = [e for e in status.sources if e.reason == "always_available"]
        assert len(mock_entries) > 0

    @pytest.mark.anyio
    async def test_with_amadeus_key(self):
        """Amadeus shows as available when keys are provided."""
        config = _default_config(
            amadeus=AmadeusConfig(api_key="test-key", api_secret="test-secret"),
        )
        registry = SourceRegistry(config)
        status = await registry.source_status()

        amadeus_entries = [e for e in status.sources if e.name == "amadeus"]
        assert len(amadeus_entries) > 0
        for entry in amadeus_entries:
            assert entry.available is True
            assert entry.reason == "configured"

    @pytest.mark.anyio
    async def test_unavailable_entries(self):
        """Amadeus without keys shows as 'not_configured'."""
        config = _default_config()
        registry = SourceRegistry(config)
        status = await registry.source_status()

        amadeus_entries = [e for e in status.sources if e.name == "amadeus"]
        assert len(amadeus_entries) > 0
        for entry in amadeus_entries:
            assert entry.available is False
            assert entry.reason == "not_configured"

    @pytest.mark.anyio
    async def test_available_names_helper(self):
        """available_names() returns correct names for a domain."""
        config = _default_config()
        registry = SourceRegistry(config)
        status = await registry.source_status()

        available = status.available_names("flights")
        assert "mock" in available

    @pytest.mark.anyio
    async def test_unavailable_names_helper(self):
        """unavailable_names() returns correct names for a domain."""
        config = _default_config()
        registry = SourceRegistry(config)
        status = await registry.source_status()

        unavailable = status.unavailable_names("flights")
        assert "amadeus" in unavailable


# ---------------------------------------------------------------------------
# TestToolOutputMockWarning
# ---------------------------------------------------------------------------

class TestToolOutputMockWarning:
    """Tool output text contains a mock/demo warning when data is mock."""

    @pytest.mark.anyio
    async def test_flights_tool_mock_warning(self):
        from smart_travel.tools.flights import search_flights_tool

        result = await search_flights_tool.handler({
            "origin": "Seattle",
            "destination": "Tokyo",
            "departure_date": "2026-06-15",
        })
        text = result["content"][0]["text"]
        assert "DEMO" in text or "MOCK" in text

    @pytest.mark.anyio
    async def test_hotels_tool_mock_warning(self):
        from smart_travel.tools.hotels import search_hotels_tool

        result = await search_hotels_tool.handler({
            "city": "Tokyo",
            "check_in": "2026-06-15",
            "check_out": "2026-06-20",
        })
        text = result["content"][0]["text"]
        assert "DEMO" in text or "MOCK" in text

    @pytest.mark.anyio
    async def test_tickets_tool_mock_warning(self):
        from smart_travel.tools.tickets import search_tickets_tool

        result = await search_tickets_tool.handler({
            "city": "Tokyo",
            "date_from": "2026-06-15",
            "date_to": "2026-06-25",
        })
        text = result["content"][0]["text"]
        assert "DEMO" in text or "MOCK" in text


# ---------------------------------------------------------------------------
# TestDynamicSystemPrompt
# ---------------------------------------------------------------------------

class TestDynamicSystemPrompt:
    """Dynamic system prompt section reflects source availability."""

    @pytest.mark.anyio
    async def test_no_keys_prompt_warns_mock(self):
        from smart_travel.agents import _build_source_status_prompt

        config = _default_config()
        registry = SourceRegistry(config)
        status = await registry.source_status()

        section = _build_source_status_prompt(status)
        assert "NO live data sources" in section

    @pytest.mark.anyio
    async def test_with_keys_prompt_shows_configured(self):
        from smart_travel.agents import _build_source_status_prompt

        config = _default_config(
            amadeus=AmadeusConfig(api_key="k", api_secret="s"),
        )
        registry = SourceRegistry(config)
        status = await registry.source_status()

        section = _build_source_status_prompt(status)
        assert "configured" in section

    @pytest.mark.anyio
    async def test_prompt_lists_all_sources(self):
        from smart_travel.agents import _build_source_status_prompt

        config = _default_config()
        registry = SourceRegistry(config)
        status = await registry.source_status()

        section = _build_source_status_prompt(status)
        assert "amadeus" in section
        assert "mock" in section


# ---------------------------------------------------------------------------
# TestDataQualityFieldInJSON
# ---------------------------------------------------------------------------

class TestDataQualityFieldInJSON:
    """Parsed JSON from tool output contains _data_quality field."""

    @pytest.mark.anyio
    async def test_flights_json_has_data_quality(self):
        from smart_travel.tools.flights import search_flights_tool

        result = await search_flights_tool.handler({
            "origin": "Seattle",
            "destination": "Tokyo",
            "departure_date": "2026-06-20",
        })
        text = result["content"][0]["text"]

        # The JSON payload starts after the notice lines — find it
        # by locating the first '['
        json_start = text.index("[")
        payload = json.loads(text[json_start:])
        assert len(payload) > 0
        for entry in payload:
            assert "_data_quality" in entry
