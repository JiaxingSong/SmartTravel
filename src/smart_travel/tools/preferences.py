"""Preference management MCP tools.

Allows the agent to save and retrieve user preferences during
conversations, enabling personalised search recommendations.
"""

from __future__ import annotations

import json

from claude_agent_sdk import tool

from smart_travel.memory.preferences import KNOWN_PREFERENCES

# Module-level memory store reference — set by agents.py before tool use
_memory_store = None


def set_memory_store(store) -> None:  # noqa: ANN001
    """Inject the active memory store so tools can access it."""
    global _memory_store
    _memory_store = store


@tool(
    "save_preference",
    "Save a user travel preference for future searches. Use this when the "
    "user mentions their home city, preferred airlines, budget range, cabin "
    "class, loyalty programs, hotel chains, or travel style. Known keys: "
    + ", ".join(KNOWN_PREFERENCES.keys()),
    {
        "key": str,
        "value": str,
    },
)
async def save_preference_tool(args: dict) -> dict:
    """Save a user preference."""
    key = args.get("key", "").strip()
    value = args.get("value", "").strip()

    if not key or not value:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Both 'key' and 'value' are required.",
                }
            ]
        }

    if _memory_store is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Memory store not available. "
                    "Preference noted but not persisted.",
                }
            ]
        }

    await _memory_store.set_preference(key, value)

    label = KNOWN_PREFERENCES.get(key, key.replace("_", " ").title())
    return {
        "content": [
            {
                "type": "text",
                "text": f"Saved preference: {label} = {value}",
            }
        ]
    }


@tool(
    "get_preferences",
    "Get all saved user travel preferences. Returns a JSON object with "
    "all known preferences.",
    {},
)
async def get_preferences_tool(args: dict) -> dict:
    """Return all saved preferences."""
    if _memory_store is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({}),
                }
            ]
        }

    prefs = await _memory_store.get_all_preferences()
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(prefs.all(), indent=2),
            }
        ]
    }
