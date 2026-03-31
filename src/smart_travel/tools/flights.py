"""Flight search MCP tool."""

from __future__ import annotations

from claude_agent_sdk import tool

from smart_travel.data.mock_flights import search_flights as _search


@tool(
    "search_flights",
    "Search for flights between cities. Returns a list of available flights "
    "with prices, airlines, departure times, and number of stops. "
    "Supports filtering by cabin class, maximum price, and maximum stops.",
    {
        "origin": str,
        "destination": str,
        "departure_date": str,
        "return_date": str,
        "cabin_class": str,
        "passengers": int,
        "max_price": float,
        "max_stops": int,
    },
)
async def search_flights_tool(args: dict) -> dict:
    """Execute flight search and return results."""
    results = _search(
        origin=args.get("origin", ""),
        destination=args.get("destination", ""),
        departure_date=args.get("departure_date", ""),
        return_date=args.get("return_date"),
        cabin_class=args.get("cabin_class", "economy"),
        passengers=args.get("passengers", 1),
        max_price=args.get("max_price"),
        max_stops=args.get("max_stops"),
    )

    if not results:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "No flights found matching your criteria. "
                    "Try adjusting your filters (higher price, more stops, different dates).",
                }
            ]
        }

    import json
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(results, indent=2),
            }
        ]
    }
