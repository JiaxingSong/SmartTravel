"""Integration tests for agent setup and tool registration."""

from __future__ import annotations

import pytest

from smart_travel.agents import create_travel_server, create_agent_options, SYSTEM_PROMPT


class TestAgentSetup:
    """Tests for agent configuration."""

    def test_system_prompt_is_non_empty(self):
        assert len(SYSTEM_PROMPT) > 100

    def test_system_prompt_mentions_tools(self):
        assert "search_flights" in SYSTEM_PROMPT
        assert "search_hotels" in SYSTEM_PROMPT
        assert "search_tickets" in SYSTEM_PROMPT
        assert "save_preference" in SYSTEM_PROMPT
        assert "get_preferences" in SYSTEM_PROMPT

    def test_create_travel_server_returns_server(self):
        server = create_travel_server()
        assert server is not None

    def test_create_agent_options_returns_options(self):
        options = create_agent_options()
        assert options is not None
        assert options.system_prompt == SYSTEM_PROMPT
        assert "travel" in options.mcp_servers


class TestToolImports:
    """Tests that tool modules can be imported correctly."""

    def test_import_flights_tool(self):
        from smart_travel.tools.flights import search_flights_tool
        assert search_flights_tool is not None

    def test_import_hotels_tool(self):
        from smart_travel.tools.hotels import search_hotels_tool
        assert search_hotels_tool is not None

    def test_import_tickets_tool(self):
        from smart_travel.tools.tickets import search_tickets_tool
        assert search_tickets_tool is not None


class TestToolExecution:
    """Tests that tool handler functions can be called directly."""

    @pytest.mark.anyio
    async def test_flights_tool_returns_content(self):
        from smart_travel.tools.flights import search_flights_tool
        result = await search_flights_tool.handler({
            "origin": "Seattle",
            "destination": "Tokyo",
            "departure_date": "2026-05-01",
        })
        assert "content" in result
        assert len(result["content"]) > 0
        assert result["content"][0]["type"] == "text"
        assert len(result["content"][0]["text"]) > 0

    @pytest.mark.anyio
    async def test_hotels_tool_returns_content(self):
        from smart_travel.tools.hotels import search_hotels_tool
        result = await search_hotels_tool.handler({
            "city": "Tokyo",
            "check_in": "2026-05-01",
            "check_out": "2026-05-05",
        })
        assert "content" in result
        assert len(result["content"]) > 0
        assert result["content"][0]["type"] == "text"

    @pytest.mark.anyio
    async def test_tickets_tool_returns_content(self):
        from smart_travel.tools.tickets import search_tickets_tool
        result = await search_tickets_tool.handler({
            "city": "Tokyo",
            "date_from": "2026-05-01",
            "date_to": "2026-05-10",
        })
        assert "content" in result
        assert len(result["content"]) > 0
        assert result["content"][0]["type"] == "text"

    @pytest.mark.anyio
    async def test_flights_tool_no_results(self):
        from smart_travel.tools.flights import search_flights_tool
        result = await search_flights_tool.handler({
            "origin": "Seattle",
            "destination": "Tokyo",
            "departure_date": "2026-05-01",
            "max_price": 1.0,  # impossibly low
        })
        assert "No flights found" in result["content"][0]["text"]

    @pytest.mark.anyio
    async def test_hotels_tool_no_results(self):
        from smart_travel.tools.hotels import search_hotels_tool
        result = await search_hotels_tool.handler({
            "city": "Tokyo",
            "check_in": "2026-05-01",
            "check_out": "2026-05-05",
            "max_price_per_night": 1.0,  # impossibly low
            "min_stars": 5,
        })
        assert "No hotels found" in result["content"][0]["text"]

    @pytest.mark.anyio
    async def test_tickets_tool_no_results(self):
        from smart_travel.tools.tickets import search_tickets_tool
        result = await search_tickets_tool.handler({
            "city": "Tokyo",
            "date_from": "2026-05-01",
            "date_to": "2026-05-10",
            "max_price": 0.01,  # impossibly low
        })
        assert "No events found" in result["content"][0]["text"]
