"""Award/points flight search MCP tool.

Dedicated tool for searching award flights across frequent flyer programs.
Queries airline websites (United, Delta, American, Alaska) for miles/points
prices.
"""

from __future__ import annotations

from claude_agent_sdk import tool

from smart_travel.data.resolver import search_flights as _search
from smart_travel.tools._formatting import format_tool_results

# All source names that return points/award data
_AWARD_SOURCE_NAMES = [
    "united_award",
    "delta_award",
    "american_award",
    "alaska_award",
]

# Map friendly program names to source names
_PROGRAM_TO_SOURCE: dict[str, str] = {
    "united": "united_award",
    "delta": "delta_award",
    "american": "american_award",
    "alaska": "alaska_award",
    "mileageplus": "united_award",
    "skymiles": "delta_award",
    "aadvantage": "american_award",
    "mileage_plan": "alaska_award",
}


@tool(
    "search_award_flights",
    "Search for award/points flights across frequent flyer programs. "
    "Queries airline websites (United, Delta, American, Alaska) for "
    "miles/points prices. "
    "Returns points costs by program with cabin class and availability. "
    "Use 'programs' to filter to specific airlines/programs.",
    {
        "origin": str,
        "destination": str,
        "departure_date": str,
        "cabin_class": str,
        "programs": list,
        "max_stops": int,
    },
)
async def search_award_flights_tool(args: dict) -> dict:
    """Execute award flight search and return results."""
    # Determine which sources to query
    programs = args.get("programs")
    if programs:
        # Map user-friendly program names to source names
        source_names = []
        for prog in programs:
            prog_lower = prog.lower().strip()
            mapped = _PROGRAM_TO_SOURCE.get(prog_lower)
            if mapped:
                source_names.append(mapped)
            elif prog_lower in _AWARD_SOURCE_NAMES:
                source_names.append(prog_lower)
        if not source_names:
            # Fallback to all award sources if no valid programs matched
            source_names = _AWARD_SOURCE_NAMES
    else:
        source_names = _AWARD_SOURCE_NAMES

    results = await _search(
        origin=args.get("origin", ""),
        destination=args.get("destination", ""),
        departure_date=args.get("departure_date", ""),
        return_date=None,
        cabin_class=args.get("cabin_class", "economy"),
        passengers=1,
        max_price=None,
        max_stops=args.get("max_stops"),
        sources=source_names,
        airlines=None,
    )

    if not results:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "No award flights found matching your criteria. "
                    "Try adjusting your filters (different dates, cabin class, "
                    "or programs). Note: airline websites may block automated "
                    "searches.",
                }
            ]
        }

    return {
        "content": [
            {
                "type": "text",
                "text": format_tool_results(results, "award flights"),
            }
        ]
    }
