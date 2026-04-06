"""MCP tool definitions for SmartTravel browser agent."""

from smart_travel.tools.browser import (
    web_search_tool,
    open_page_tool,
    fill_form_tool,
    monitor_price_tool,
)
from smart_travel.tools.preferences import save_preference_tool, get_preferences_tool

__all__ = [
    "web_search_tool",
    "open_page_tool",
    "fill_form_tool",
    "monitor_price_tool",
    "save_preference_tool",
    "get_preferences_tool",
]
