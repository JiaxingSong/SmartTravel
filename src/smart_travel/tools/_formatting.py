"""Shared formatting helpers for MCP tool output.

Adds data-quality notices when results include mock/demo data,
so the agent (and ultimately the user) can distinguish real from
fabricated information.
"""

from __future__ import annotations

import json
from typing import Any


def format_tool_results(results: list[dict[str, Any]], domain: str) -> str:
    """Format search results as JSON text with a data-quality preamble.

    Parameters
    ----------
    results:
        List of result dicts.  Each should carry a ``_data_quality``
        field (``"live"`` or ``"mock"``).
    domain:
        ``"flights"``, ``"hotels"``, or ``"tickets"`` — used in the
        notice wording.

    Returns
    -------
    str
        Human-readable text block containing an optional data-quality
        notice followed by the JSON payload.
    """
    qualities = {r.get("_data_quality", "unknown") for r in results}
    sources_seen = sorted({r.get("source", "unknown") for r in results})
    sources_line = f"Sources: {', '.join(sources_seen)}"

    parts: list[str] = []

    if qualities == {"mock"}:
        parts.append(
            f"\u26a0\ufe0f DATA QUALITY NOTICE: These {domain} results are "
            "DEMO/MOCK data generated for illustration purposes only. "
            "They do NOT reflect real availability or pricing. "
            "No live data sources are configured for this search."
        )
    elif "mock" in qualities and "live" in qualities:
        parts.append(
            f"\u2139\ufe0f DATA QUALITY NOTICE: These {domain} results come "
            "from a MIX of live and demo/mock sources. Check the "
            "\"_data_quality\" field on each result: \"live\" means real "
            "data, \"mock\" means demo data."
        )

    parts.append(sources_line)
    parts.append(json.dumps(results, indent=2))

    return "\n\n".join(parts)
