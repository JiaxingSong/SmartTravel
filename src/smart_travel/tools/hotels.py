"""Hotel search MCP tool."""

from __future__ import annotations

from claude_agent_sdk import tool

from smart_travel.data.mock_hotels import search_hotels as _search


@tool(
    "search_hotels",
    "Search for hotels in a city. Returns a list of available hotels with "
    "prices, star ratings, guest ratings, amenities, and neighborhood. "
    "Supports filtering by star rating, maximum price, and required amenities.",
    {
        "city": str,
        "check_in": str,
        "check_out": str,
        "guests": int,
        "rooms": int,
        "min_stars": int,
        "max_price_per_night": float,
        "required_amenities": list,
    },
)
async def search_hotels_tool(args: dict) -> dict:
    """Execute hotel search and return results."""
    # Parse required_amenities properly
    amenities = args.get("required_amenities")
    if isinstance(amenities, str):
        amenities = [a.strip() for a in amenities.split(",")]

    results = _search(
        city=args.get("city", ""),
        check_in=args.get("check_in", ""),
        check_out=args.get("check_out", ""),
        guests=args.get("guests", 1),
        rooms=args.get("rooms", 1),
        min_stars=args.get("min_stars"),
        max_price_per_night=args.get("max_price_per_night"),
        required_amenities=amenities,
    )

    if not results:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "No hotels found matching your criteria. "
                    "Try adjusting your filters (lower star rating, higher price, fewer amenities).",
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
