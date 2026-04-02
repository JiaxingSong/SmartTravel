"""User preference storage and system-prompt formatting.

Preferences are key-value pairs that the agent learns during conversations
(e.g. home city, preferred airlines, budget range).  They are injected into
the system prompt so the agent can personalise responses across sessions.
"""

from __future__ import annotations

from typing import Any


# Well-known preference keys with human-readable descriptions
KNOWN_PREFERENCES: dict[str, str] = {
    "home_city": "Home city for default origin",
    "preferred_airlines": "Preferred airlines (comma-separated IATA codes)",
    "preferred_cabin": "Default cabin class (economy/premium_economy/business/first)",
    "budget_range": "Travel budget range (e.g. 'moderate', '$500-$1000')",
    "loyalty_programs": "Loyalty programs (comma-separated, e.g. 'united,marriott')",
    "hotel_chains": "Preferred hotel chains (comma-separated)",
    "travel_style": "Travel style (e.g. 'luxury', 'budget', 'adventure')",
}


class UserPreferences:
    """Dict-like wrapper for user preferences with prompt generation."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = dict(data) if data else {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def all(self) -> dict[str, Any]:
        return dict(self._data)

    def __bool__(self) -> bool:
        return bool(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def to_prompt_section(self) -> str:
        """Format preferences as a markdown section for system prompt injection.

        Returns an empty string if no preferences are set.
        """
        if not self._data:
            return ""

        lines = ["\n## User preferences\n"]
        lines.append("The user has saved the following preferences. "
                      "Use these to personalise searches and recommendations:\n")

        for key, value in sorted(self._data.items()):
            label = KNOWN_PREFERENCES.get(key, key.replace("_", " ").title())
            lines.append(f"- **{label}**: {value}")

        return "\n".join(lines)
