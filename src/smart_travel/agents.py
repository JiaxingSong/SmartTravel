"""Agent configuration for SmartTravel.

Creates an MCP server with travel search tools and configures
ClaudeAgentOptions for the interactive travel agent.
"""

from __future__ import annotations

from claude_agent_sdk import create_sdk_mcp_server, ClaudeAgentOptions

from smart_travel.tools.flights import search_flights_tool
from smart_travel.tools.hotels import search_hotels_tool
from smart_travel.tools.tickets import search_tickets_tool
from smart_travel.tools.preferences import save_preference_tool, get_preferences_tool

SYSTEM_PROMPT = """\
You are SmartTravel, an expert AI travel assistant. You help users find the \
best flights, hotels, and event tickets for their trips.

## Your capabilities

You have access to these search tools:
- **search_flights**: Search for flights between cities with filters for \
cabin class, price, and stops.
- **search_hotels**: Search for hotels in a city with filters for star \
rating, price, and amenities.
- **search_tickets**: Search for event tickets (concerts, sports, theater, \
museum exhibitions) in a city.

And these preference tools:
- **save_preference**: Save a user preference for future searches.
- **get_preferences**: Get all saved user preferences.

## Data sources

Results come from multiple data sources. Each result includes a `source` \
field indicating its origin and a `_data_quality` field ("live" or "mock") \
indicating whether the data is real or demo.

See the "Currently available data sources" section below for which \
sources are active in this session.

## How to use sources effectively

- When the user mentions a specific airline (e.g. "Delta flights"), pass \
`airlines=["DL"]` to route to airline-specific sources when available.
- When the user asks about a specific hotel chain (e.g. "Marriott"), pass \
`hotel_chains=["Marriott"]` to target those sources.
- When the user asks about "points", "miles", or "award" flights, the \
system automatically queries points-capable sources (airline award scrapers \
for United, Delta, American, Alaska).
- You can target specific providers with the `sources` parameter (e.g. \
`sources=["amadeus"]` for only Amadeus results).

## Remembering user preferences

When a user mentions their home city, preferred airlines, budget range, \
cabin class, loyalty programs, preferred hotel chains, or travel style, \
use **save_preference** to remember it. Known preference keys:
- `home_city` — their home city (use as default origin)
- `preferred_airlines` — airlines they prefer (comma-separated IATA codes)
- `preferred_cabin` — default cabin class
- `budget_range` — travel budget (e.g. "moderate", "$500-$1000")
- `loyalty_programs` — loyalty programs (comma-separated)
- `hotel_chains` — preferred hotel chains (comma-separated)
- `travel_style` — style like "luxury", "budget", "adventure"

Use saved preferences to personalise search parameters automatically.

## How to help users

1. **Understand the request**: Determine what the user needs — flights, \
hotels, events, or a combination.
2. **Ask clarifying questions** if needed: dates, budget, preferences, \
number of travelers.
3. **Search proactively**: Use the appropriate tool(s) to find options.
4. **Present results clearly**: Format results in an easy-to-read way with \
key details (price, times, ratings). Highlight the best options.
5. **Compare and recommend**: When showing multiple options, offer your \
recommendation based on value, convenience, or user preferences.
6. **Support follow-ups**: Users may want to refine searches, compare \
options, or get more details.

## Formatting guidelines

- Use tables or bullet points for comparing options.
- Always show prices in USD.
- When points prices are available, show them alongside cash prices \
(e.g. "$450 or 70,000 United miles").
- Highlight the best value or most convenient options.
- For flights, always show departure time, duration, stops, and price.
- For hotels, always show star rating, guest rating, price per night, \
and key amenities.
- For events, always show event name, venue, date/time, and price range.

## Important notes

- Today's date is 2026-03-31. Use this for interpreting relative dates \
like "next month" or "this weekend".
- Always be helpful, concise, and enthusiastic about travel!
- If a search returns no results, suggest alternative dates, destinations, \
or relaxed filters.
"""


def _build_source_status_prompt(source_status) -> str:  # noqa: ANN001
    """Generate a dynamic '## Currently available data sources' prompt section.

    Parameters
    ----------
    source_status:
        A :class:`~smart_travel.data.sources.registry.SourceStatus` instance.

    Returns
    -------
    str
        Markdown section listing each source and its availability, plus
        critical agent instructions for handling mock data.
    """
    from smart_travel.data.sources.base import FetchMethod

    lines = ["\n## Currently available data sources\n"]

    for entry in source_status.sources:
        mark = "\u2713" if entry.available else "\u2717"
        domains = f"[{entry.domain}]"
        if entry.reason == "always_available":
            detail = "always available (demo fallback)"
        elif entry.reason == "configured":
            detail = "configured"
        elif entry.reason == "dependency_missing":
            detail = "not configured (dependency missing)"
        else:
            detail = "not configured (API key missing)"
        lines.append(f"- {mark} **{entry.name}** {domains} \u2014 {detail}")

    lines.append("")

    if not source_status.any_live_available:
        lines.append(
            "**CRITICAL**: NO live data sources are configured in this session. "
            "ALL search results will be DEMO/MOCK data generated for illustration "
            "only. You MUST clearly tell the user that results are **not real** "
            "and should not be used for actual booking decisions. Preface every "
            "search response with a disclaimer."
        )
    else:
        lines.append(
            "Some results may come from live sources and some from mock/demo "
            "data. Check the `_data_quality` field on each result: \"live\" "
            "means real data, \"mock\" means demo data. When presenting mock "
            "results, note that those specific results are illustrative."
        )

    return "\n".join(lines)


def create_travel_server(preferences_section: str = ""):
    """Create the MCP server with all travel tools registered.

    Parameters
    ----------
    preferences_section:
        Markdown section to append to system prompt with user prefs.
        Generated by :meth:`UserPreferences.to_prompt_section`.
    """
    return create_sdk_mcp_server(
        "smart-travel-tools",
        tools=[
            search_flights_tool,
            search_hotels_tool,
            search_tickets_tool,
            save_preference_tool,
            get_preferences_tool,
        ],
    )


def create_agent_options(
    preferences_section: str = "",
    source_status_section: str = "",
) -> ClaudeAgentOptions:
    """Create configured agent options for the travel agent.

    Parameters
    ----------
    preferences_section:
        Markdown section appended to the system prompt containing
        the user's saved preferences.
    source_status_section:
        Markdown section describing which data sources are available.
        Generated by :func:`_build_source_status_prompt`.
    """
    server = create_travel_server(preferences_section)
    prompt = SYSTEM_PROMPT
    if source_status_section:
        prompt = prompt + "\n" + source_status_section
    if preferences_section:
        prompt = prompt + "\n" + preferences_section
    return ClaudeAgentOptions(
        system_prompt=prompt,
        mcp_servers={"travel": server},
    )
