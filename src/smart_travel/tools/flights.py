"""Flight search MCP tool."""

from __future__ import annotations

from claude_agent_sdk import tool

from smart_travel.data.resolver import search_flights as _search
from smart_travel.tools._formatting import format_tool_results


@tool(
    "search_flights",
    "Search for flights between cities. Returns a list of available flights "
    "with prices, airlines, departure times, and number of stops. "
    "Supports filtering by cabin class, maximum price, and maximum stops. "
    "Results may include cash prices and/or points/miles prices from "
    "multiple sources. Use 'sources' to target specific providers and "
    "'airlines' to filter by IATA airline code.",
    {
        "origin": str,
        "destination": str,
        "departure_date": str,
        "return_date": str,
        "cabin_class": str,
        "passengers": int,
        "max_price": float,
        "max_stops": int,
        "sources": list,
        "airlines": list,
    },
)
async def search_flights_tool(args: dict) -> dict:
    """Execute flight search and return results."""
    results = await _search(
        origin=args.get("origin", ""),
        destination=args.get("destination", ""),
        departure_date=args.get("departure_date", ""),
        return_date=args.get("return_date"),
        cabin_class=args.get("cabin_class", "economy"),
        passengers=args.get("passengers", 1),
        max_price=args.get("max_price"),
        max_stops=args.get("max_stops"),
        sources=args.get("sources"),
        airlines=args.get("airlines"),
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

    return {
        "content": [
            {
                "type": "text",
                "text": format_tool_results(results, "flights"),
            }
        ]
    }
