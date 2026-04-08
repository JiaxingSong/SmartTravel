"""Public award chart data for domestic US airline loyalty programs.

Most airlines publish fixed award charts for standard/saver redemptions.
This module provides the published rates so award pricing can be estimated
without logging into airline sites. Delta uses dynamic pricing and cannot
be estimated from a chart.

Sources:
- United: https://www.united.com/ual/en/us/fly/mileageplus/awards/travel/chart.html
- Alaska: https://www.alaskaair.com/content/mileage-plan/use-miles/award-charts
- AA: https://www.aa.com/i18n/aadvantage-program/miles/redeem/award-travel/flight-award-chart.jsp
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AwardChartEntry:
    """A single entry in an airline's award chart."""
    program: str
    cabin: str           # "economy" | "premium_economy" | "business" | "first"
    region: str          # "domestic_short" | "domestic_long" | "international"
    miles_low: int       # saver/lowest
    miles_high: int      # standard/highest
    is_dynamic: bool     # True if prices vary (e.g. Delta)
    notes: str = ""


# ---------------------------------------------------------------------------
# Award charts (as of 2026)
# ---------------------------------------------------------------------------

UNITED_CHART: list[AwardChartEntry] = [
    AwardChartEntry("MileagePlus", "economy", "domestic_short", 10000, 12500, False, "under 700 miles"),
    AwardChartEntry("MileagePlus", "economy", "domestic_long", 12500, 35000, False, "saver 12.5k, standard up to 35k"),
    AwardChartEntry("MileagePlus", "business", "domestic_long", 25000, 70000, False, "polaris domestic"),
    AwardChartEntry("MileagePlus", "first", "domestic_long", 35000, 80000, False),
]

ALASKA_CHART: list[AwardChartEntry] = [
    AwardChartEntry("Mileage Plan", "economy", "domestic_short", 5000, 7500, False, "under 700 miles"),
    AwardChartEntry("Mileage Plan", "economy", "domestic_long", 7500, 25000, False, "saver 7.5k, standard up to 25k"),
    AwardChartEntry("Mileage Plan", "business", "domestic_long", 15000, 50000, False),
    AwardChartEntry("Mileage Plan", "first", "domestic_long", 25000, 60000, False),
]

AA_CHART: list[AwardChartEntry] = [
    AwardChartEntry("AAdvantage", "economy", "domestic_short", 7500, 12500, False, "web special / saver"),
    AwardChartEntry("AAdvantage", "economy", "domestic_long", 12500, 35000, False, "MileSAAver / standard"),
    AwardChartEntry("AAdvantage", "business", "domestic_long", 25000, 57500, False),
    AwardChartEntry("AAdvantage", "first", "domestic_long", 32500, 70000, False),
]

DELTA_CHART: list[AwardChartEntry] = [
    AwardChartEntry("SkyMiles", "economy", "domestic_short", 5000, 40000, True, "dynamic pricing, varies by route/date"),
    AwardChartEntry("SkyMiles", "economy", "domestic_long", 8000, 60000, True, "dynamic pricing"),
    AwardChartEntry("SkyMiles", "business", "domestic_long", 15000, 100000, True, "dynamic pricing"),
    AwardChartEntry("SkyMiles", "first", "domestic_long", 25000, 150000, True, "dynamic pricing"),
]

_CHARTS: dict[str, list[AwardChartEntry]] = {
    "united": UNITED_CHART,
    "alaska": ALASKA_CHART,
    "aa": AA_CHART,
    "american": AA_CHART,
    "delta": DELTA_CHART,
}


def estimate_award_price(
    airline: str,
    cabin: str = "economy",
    distance_miles: int = 1500,
) -> AwardChartEntry | None:
    """Look up the published award chart entry for a domestic route.

    Args:
        airline: canonical key ("united", "alaska", "delta", "aa")
        cabin: "economy", "business", or "first"
        distance_miles: approximate route distance (used for short vs long haul)

    Returns:
        The matching AwardChartEntry, or None if not found.
    """
    chart = _CHARTS.get(airline.lower())
    if not chart:
        return None

    region = "domestic_short" if distance_miles < 700 else "domestic_long"
    cabin = cabin.lower()

    for entry in chart:
        if entry.cabin == cabin and entry.region == region:
            return entry

    # Fallback to domestic_long if short not found
    for entry in chart:
        if entry.cabin == cabin and entry.region == "domestic_long":
            return entry

    return None


def format_award_estimate(
    airline: str,
    program: str,
    origin: str,
    dest: str,
    cabin: str = "economy",
    distance_miles: int = 1500,
) -> str:
    """Format a human-readable award price estimate."""
    entry = estimate_award_price(airline, cabin, distance_miles)
    if not entry:
        return f"{program}: no award chart data available"

    if entry.is_dynamic:
        return (
            f"{program}: {entry.miles_low:,}-{entry.miles_high:,} miles (dynamic pricing, "
            f"actual price varies by date/demand)"
        )
    else:
        return (
            f"{program}: {entry.miles_low:,}-{entry.miles_high:,} miles "
            f"(saver-standard range)"
        )
