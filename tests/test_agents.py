"""Tests for the browser-agent setup in agents.py."""
from __future__ import annotations

from smart_travel.agents import create_agent_options, SYSTEM_PROMPT


class TestSystemPrompt:
    def test_non_empty(self) -> None:
        assert len(SYSTEM_PROMPT) > 100

    def test_mentions_browser_tools(self) -> None:
        assert "web_search" in SYSTEM_PROMPT
        assert "open_page" in SYSTEM_PROMPT
        assert "fill_form" in SYSTEM_PROMPT
        assert "monitor_price" in SYSTEM_PROMPT

    def test_does_not_mention_old_tools(self) -> None:
        assert "search_flights" not in SYSTEM_PROMPT
        assert "search_hotels" not in SYSTEM_PROMPT
        assert "search_tickets" not in SYSTEM_PROMPT
        assert "Amadeus" not in SYSTEM_PROMPT
        assert "Ticketmaster" not in SYSTEM_PROMPT
        assert "_data_quality" not in SYSTEM_PROMPT

    def test_mentions_travel_sites(self) -> None:
        assert "Kayak" in SYSTEM_PROMPT or "Google Flights" in SYSTEM_PROMPT


class TestCreateAgentOptions:
    def test_returns_options(self) -> None:
        options = create_agent_options()
        assert options is not None

    def test_mcp_server_registered(self) -> None:
        options = create_agent_options()
        assert "travel" in options.mcp_servers

    def test_preferences_section_appended(self) -> None:
        options = create_agent_options(preferences_section="## Prefs\n- home: Seattle")
        assert "home: Seattle" in options.system_prompt

    def test_no_preferences_section_clean_prompt(self) -> None:
        options = create_agent_options()
        assert options.system_prompt == SYSTEM_PROMPT
