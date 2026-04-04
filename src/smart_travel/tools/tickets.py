"""Event/ticket search MCP tool."""

from __future__ import annotations

from claude_agent_sdk import tool

from smart_travel.data.resolver import search_tickets as _search
from smart_travel.tools._formatting import format_tool_results


@tool(
    "search_tickets",
    "Search for event tickets (concerts, sports, theater, museum exhibitions) "
    "in a city within a date range. Returns a list of events with prices, "
    "venues, dates, and ratings. Supports filtering by event type, maximum "
    "price, and minimum rating. Use 'sources' to target specific providers.",
    {
        "city": str,
        "date_from": str,
        "date_to": str,
        "event_type": str,
        "max_price": float,
        "min_rating": float,
        "sources": list,
    },
)
async def search_tickets_tool(args: dict) -> dict:
    """Execute ticket search and return results."""
    results = await _search(
        city=args.get("city", ""),
        date_from=args.get("date_from", ""),
        date_to=args.get("date_to", ""),
        event_type=args.get("event_type"),
        max_price=args.get("max_price"),
        min_rating=args.get("min_rating"),
        sources=args.get("sources"),
    )

    if not results:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "No events found matching your criteria. "
                    "Try adjusting your filters (wider date range, higher price limit, different event type).",
                }
            ]
        }

    return {
        "content": [
            {
                "type": "text",
                "text": format_tool_results(results, "tickets"),
            }
        ]
    }
