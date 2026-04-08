"""Global award chart database — 26 airline loyalty programs.

Provides published award chart rates for all major programs in North America,
Asia, and Europe. For a given flight, generates all possible redemption options
across own-metal and partner programs (the N dimension of the M×N matrix).

Key concepts:
- A "route_region" (domestic, transatlantic, transpacific, etc.) determines
  which chart rates apply.
- Each program has rates for own-metal and partner bookings per region/cabin.
- Programs in the same alliance can book each other's flights.
- Some programs have special (non-alliance) partner agreements.

All rates are one-way in miles/points. Ranges reflect saver-to-standard.
Dynamic programs show typical observed low/high.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from smart_travel.data.alliances import (
    get_bookable_programs,
    get_transfer_sources,
    normalize_airline,
    AIRLINE_INFO,
    SPECIAL_PARTNERS,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ChartRate:
    """Award chart rate for a specific program/region/cabin combination."""
    miles_low: int       # saver / lowest published
    miles_high: int      # standard / highest published
    is_dynamic: bool = False
    notes: str = ""


@dataclass
class ProgramChart:
    """Complete award chart for one loyalty program."""
    program_name: str    # "MileagePlus"
    airline_key: str     # "united"
    # Nested: route_region → cabin → ChartRate
    # Cabins: "economy", "premium_economy", "business", "first"
    rates: dict[str, dict[str, ChartRate]] = field(default_factory=dict)
    # Own-metal vs partner rates (some programs charge more for partners)
    partner_surcharge_pct: int = 0  # 0 = same rate, 10 = 10% more for partners

    def get_rate(self, route_region: str, cabin: str) -> ChartRate | None:
        """Look up the rate for a region/cabin. Falls back to 'international'."""
        region_rates = self.rates.get(route_region)
        if not region_rates:
            region_rates = self.rates.get("international")
        if not region_rates:
            return None
        rate = region_rates.get(cabin.lower())
        if not rate:
            rate = region_rates.get("economy")  # fallback to economy
        return rate


@dataclass
class RedemptionOption:
    """One way to book a specific flight using miles/points."""
    program_name: str          # "MileagePlus"
    program_airline: str       # "united"
    miles_required: int        # 12500
    miles_high: int            # 35000 (standard/peak)
    taxes_usd: float           # 5.60
    booking_type: str          # "own_metal" | "partner" | "special_partner"
    is_dynamic: bool           # False
    is_estimate: bool          # True (chart-based, not live)
    transfer_partners: list[str]  # ["Chase Ultimate Rewards", "Amex MR"]
    cents_per_mile: float      # cash_price / miles * 100
    notes: str = ""


# ---------------------------------------------------------------------------
# Program charts — North America
# ---------------------------------------------------------------------------

_R = ChartRate  # shorthand

PROGRAMS: dict[str, ProgramChart] = {}


def _add(key: str, name: str, rates: dict) -> None:
    PROGRAMS[key] = ProgramChart(program_name=name, airline_key=key, rates=rates)


# United MileagePlus
_add("united", "MileagePlus", {
    "domestic": {
        "economy": _R(12500, 35000), "business": _R(25000, 70000), "first": _R(35000, 80000),
    },
    "transatlantic": {
        "economy": _R(30000, 70000), "business": _R(60000, 140000), "first": _R(80000, 180000),
    },
    "transpacific": {
        "economy": _R(35000, 80000), "business": _R(70000, 160000), "first": _R(90000, 200000),
    },
    "international": {
        "economy": _R(30000, 70000), "business": _R(60000, 140000), "first": _R(80000, 180000),
    },
})

# Delta SkyMiles (fully dynamic)
_add("delta", "SkyMiles", {
    "domestic": {
        "economy": _R(8000, 60000, True), "business": _R(15000, 100000, True),
        "first": _R(25000, 150000, True),
    },
    "transatlantic": {
        "economy": _R(25000, 120000, True), "business": _R(50000, 240000, True),
        "first": _R(75000, 350000, True),
    },
    "transpacific": {
        "economy": _R(30000, 140000, True), "business": _R(60000, 280000, True),
        "first": _R(85000, 400000, True),
    },
    "international": {
        "economy": _R(25000, 120000, True), "business": _R(50000, 240000, True),
    },
})

# American AAdvantage
_add("american", "AAdvantage", {
    "domestic": {
        "economy": _R(12500, 35000), "business": _R(25000, 57500), "first": _R(32500, 70000),
    },
    "transatlantic": {
        "economy": _R(30000, 65000), "business": _R(57500, 115000), "first": _R(85000, 145000),
    },
    "transpacific": {
        "economy": _R(35000, 75000), "business": _R(60000, 130000), "first": _R(100000, 175000),
    },
    "international": {
        "economy": _R(30000, 65000), "business": _R(57500, 115000),
    },
})

# Alaska Mileage Plan (now Atmos Rewards, dynamic)
_add("alaska", "Mileage Plan", {
    "domestic": {
        "economy": _R(7500, 25000, True), "business": _R(15000, 50000, True),
        "first": _R(25000, 60000, True),
    },
    "transatlantic": {
        "economy": _R(22500, 55000, True), "business": _R(42500, 100000, True),
    },
    "transpacific": {
        "economy": _R(25000, 60000, True), "business": _R(50000, 110000, True),
        "first": _R(70000, 140000, True),
    },
    "international": {
        "economy": _R(22500, 55000, True), "business": _R(42500, 100000, True),
    },
})

# Air Canada Aeroplan (fixed chart, excellent value)
_add("air_canada", "Aeroplan", {
    "domestic": {
        "economy": _R(12500, 25000), "business": _R(25000, 40000),
    },
    "transatlantic": {
        "economy": _R(30000, 50000), "business": _R(55000, 80000),
        "first": _R(70000, 100000),
    },
    "transpacific": {
        "economy": _R(35000, 55000), "business": _R(60000, 90000),
        "first": _R(75000, 110000),
    },
    "international": {
        "economy": _R(30000, 50000), "business": _R(55000, 80000),
    },
})

# Southwest Rapid Rewards (revenue-based)
_add("southwest", "Rapid Rewards", {
    "domestic": {"economy": _R(5000, 25000, True, "revenue-based ~1.3cpp")},
})

# JetBlue TrueBlue (revenue-based)
_add("jetblue", "TrueBlue", {
    "domestic": {"economy": _R(4000, 20000, True, "revenue-based ~1.3cpp")},
    "transatlantic": {"economy": _R(12000, 60000, True, "Mint/economy")},
})


# ---------------------------------------------------------------------------
# Program charts — Asia
# ---------------------------------------------------------------------------

# ANA Mileage Club (fixed chart, famous sweet spots)
_add("ana", "ANA Mileage Club", {
    "domestic": {
        "economy": _R(5000, 10000), "business": _R(10000, 20000),
    },
    "transpacific": {
        "economy": _R(35000, 50000), "business": _R(75000, 90000),
        "first": _R(105000, 165000, False, "ANA first class sweet spot"),
    },
    "transatlantic": {
        "economy": _R(30000, 45000), "business": _R(63000, 88000),
        "first": _R(88000, 165000),
    },
    "intra_asia": {
        "economy": _R(10000, 18000), "business": _R(25000, 38000),
    },
    "international": {
        "economy": _R(30000, 50000), "business": _R(63000, 90000),
        "first": _R(88000, 165000),
    },
})

# JAL Mileage Bank
_add("jal", "JAL Mileage Bank", {
    "transpacific": {
        "economy": _R(25000, 40000), "business": _R(60000, 80000),
        "first": _R(100000, 120000),
    },
    "intra_asia": {
        "economy": _R(7500, 15000), "business": _R(18000, 36000),
    },
    "international": {
        "economy": _R(25000, 40000), "business": _R(60000, 80000),
        "first": _R(100000, 120000),
    },
})

# Cathay Pacific Asia Miles
_add("cathay", "Asia Miles", {
    "transpacific": {
        "economy": _R(30000, 50000), "business": _R(65000, 90000),
        "first": _R(110000, 140000),
    },
    "intra_asia": {
        "economy": _R(10000, 20000), "business": _R(25000, 45000),
        "first": _R(40000, 65000),
    },
    "international": {
        "economy": _R(30000, 50000), "business": _R(65000, 90000),
        "first": _R(110000, 140000),
    },
})

# Singapore KrisFlyer
_add("singapore", "KrisFlyer", {
    "transpacific": {
        "economy": _R(27500, 50000), "business": _R(62000, 92000),
        "first": _R(95000, 145000),
    },
    "intra_asia": {
        "economy": _R(10000, 18000), "business": _R(22000, 40000),
    },
    "international": {
        "economy": _R(27500, 50000), "business": _R(62000, 92000),
        "first": _R(95000, 145000),
    },
})

# Korean Air SKYPASS (great value for first class)
_add("korean_air", "SKYPASS", {
    "transpacific": {
        "economy": _R(25000, 40000), "business": _R(50000, 70000),
        "first": _R(80000, 100000, False, "excellent first class value"),
    },
    "intra_asia": {
        "economy": _R(7500, 15000), "business": _R(15000, 30000),
    },
    "international": {
        "economy": _R(25000, 40000), "business": _R(50000, 70000),
        "first": _R(80000, 100000),
    },
})

# EVA Air Infinity MileageLands
_add("eva", "Infinity MileageLands", {
    "transpacific": {
        "economy": _R(25000, 45000), "business": _R(65000, 90000),
        "first": _R(90000, 120000),
    },
    "intra_asia": {
        "economy": _R(10000, 18000), "business": _R(20000, 40000),
    },
    "international": {
        "economy": _R(25000, 45000), "business": _R(65000, 90000),
    },
})

# China Airlines Dynasty Flyer
_add("china_airlines", "Dynasty Flyer", {
    "transpacific": {
        "economy": _R(25000, 45000), "business": _R(55000, 80000),
    },
    "intra_asia": {
        "economy": _R(8000, 15000), "business": _R(20000, 35000),
    },
    "international": {
        "economy": _R(25000, 45000), "business": _R(55000, 80000),
    },
})

# Thai Royal Orchid Plus
_add("thai", "Royal Orchid Plus", {
    "transpacific": {
        "economy": _R(25000, 50000), "business": _R(55000, 80000),
        "first": _R(80000, 120000),
    },
    "intra_asia": {
        "economy": _R(8000, 15000), "business": _R(20000, 35000),
    },
    "international": {
        "economy": _R(25000, 50000), "business": _R(55000, 80000),
    },
})

# Malaysia Airlines Enrich
_add("malaysia", "Enrich", {
    "transpacific": {
        "economy": _R(25000, 50000), "business": _R(55000, 85000),
        "first": _R(90000, 130000),
    },
    "intra_asia": {
        "economy": _R(8000, 15000), "business": _R(18000, 35000),
    },
    "international": {
        "economy": _R(25000, 50000), "business": _R(55000, 85000),
    },
})

# Air India Flying Returns
_add("air_india", "Flying Returns", {
    "transpacific": {
        "economy": _R(20000, 40000), "business": _R(50000, 75000),
        "first": _R(75000, 100000),
    },
    "intra_asia": {
        "economy": _R(8000, 15000), "business": _R(18000, 30000),
    },
    "international": {
        "economy": _R(20000, 40000), "business": _R(50000, 75000),
    },
})


# ---------------------------------------------------------------------------
# Program charts — Europe
# ---------------------------------------------------------------------------

# British Airways Avios (distance-based)
_add("british_airways", "Avios", {
    "domestic": {
        "economy": _R(6500, 13000, False, "distance-based"),
        "business": _R(13000, 26000, False, "distance-based"),
    },
    "transatlantic": {
        "economy": _R(13000, 26000), "business": _R(26000, 52000),
        "first": _R(51000, 68000),
    },
    "intra_europe": {
        "economy": _R(6500, 13000, False, "short-haul sweet spot"),
        "business": _R(13000, 20000),
    },
    "international": {
        "economy": _R(13000, 26000), "business": _R(26000, 52000),
        "first": _R(51000, 68000),
    },
})

# Lufthansa Miles & More
_add("lufthansa", "Miles & More", {
    "intra_europe": {
        "economy": _R(10000, 20000), "business": _R(20000, 40000),
    },
    "transatlantic": {
        "economy": _R(23000, 46000), "business": _R(55000, 112000),
        "first": _R(85000, 170000),
    },
    "transpacific": {
        "economy": _R(23000, 46000), "business": _R(55000, 112000),
        "first": _R(85000, 170000),
    },
    "international": {
        "economy": _R(23000, 46000), "business": _R(55000, 112000),
        "first": _R(85000, 170000),
    },
})

# Air France/KLM Flying Blue (dynamic)
_add("air_france", "Flying Blue", {
    "intra_europe": {
        "economy": _R(6000, 20000, True), "business": _R(12000, 40000, True),
    },
    "transatlantic": {
        "economy": _R(15000, 50000, True), "business": _R(50000, 120000, True),
        "first": _R(75000, 180000, True, "La Premiere"),
    },
    "international": {
        "economy": _R(15000, 50000, True), "business": _R(50000, 120000, True),
    },
})

# Turkish Miles&Smiles (fixed chart, excellent value)
_add("turkish", "Miles&Smiles", {
    "domestic": {
        "economy": _R(7500, 12500), "business": _R(12500, 25000),
    },
    "transatlantic": {
        "economy": _R(15000, 30000), "business": _R(45000, 70000),
    },
    "transpacific": {
        "economy": _R(17500, 35000), "business": _R(45000, 70000),
        "first": _R(70000, 100000),
    },
    "europe_asia": {
        "economy": _R(12500, 25000), "business": _R(30000, 55000),
    },
    "international": {
        "economy": _R(15000, 30000), "business": _R(45000, 70000),
        "first": _R(70000, 100000),
    },
})

# Iberia Avios (distance-based, similar to BA but sometimes cheaper)
_add("iberia", "Avios (Iberia)", {
    "transatlantic": {
        "economy": _R(17000, 34000), "business": _R(34000, 68000),
        "first": _R(51000, 102000),
    },
    "intra_europe": {
        "economy": _R(5000, 10000, False, "Iberia short-haul sweet spot"),
        "business": _R(10000, 17000),
    },
    "international": {
        "economy": _R(17000, 34000), "business": _R(34000, 68000),
    },
})

# Virgin Atlantic Flying Club
_add("virgin_atlantic", "Flying Club", {
    "transatlantic": {
        "economy": _R(15000, 30000), "business": _R(47500, 72500),
        "first": _R(72500, 100000),
    },
    "transpacific": {
        "economy": _R(20000, 40000), "business": _R(47500, 80000),
        "first": _R(72500, 110000, False, "ANA F via VS sweet spot"),
    },
    "international": {
        "economy": _R(15000, 40000), "business": _R(47500, 80000),
    },
})

# SAS EuroBonus
_add("sas", "EuroBonus", {
    "intra_europe": {
        "economy": _R(8000, 15000), "business": _R(15000, 30000),
    },
    "transatlantic": {
        "economy": _R(20000, 40000), "business": _R(60000, 80000),
    },
    "international": {
        "economy": _R(20000, 40000), "business": _R(60000, 80000),
    },
})

# Finnair Plus
_add("finnair", "Finnair Plus", {
    "intra_europe": {
        "economy": _R(7500, 15000), "business": _R(15000, 30000),
    },
    "transatlantic": {
        "economy": _R(20000, 40000), "business": _R(56000, 72000),
    },
    "europe_asia": {
        "economy": _R(20000, 40000), "business": _R(45000, 70000),
        "first": _R(72000, 100000),
    },
    "international": {
        "economy": _R(20000, 40000), "business": _R(56000, 72000),
    },
})

# TAP Miles&Go
_add("tap", "Miles&Go", {
    "intra_europe": {
        "economy": _R(10000, 20000), "business": _R(20000, 40000),
    },
    "transatlantic": {
        "economy": _R(20000, 40000), "business": _R(50000, 70000),
    },
    "international": {
        "economy": _R(20000, 40000), "business": _R(50000, 70000),
    },
})

# Avianca LifeMiles (Star Alliance, great partner value)
_add("avianca", "LifeMiles", {
    "domestic": {
        "economy": _R(7500, 15000), "business": _R(15000, 30000),
    },
    "transatlantic": {
        "economy": _R(20000, 35000), "business": _R(50000, 70000),
    },
    "transpacific": {
        "economy": _R(25000, 40000), "business": _R(60000, 80000),
        "first": _R(87000, 120000),
    },
    "international": {
        "economy": _R(20000, 40000), "business": _R(50000, 80000),
    },
})


# ---------------------------------------------------------------------------
# M×N generator
# ---------------------------------------------------------------------------

def get_redemption_options(
    operating_airline: str,
    cabin: str,
    route_region: str,
    cash_price_usd: float = 0.0,
    taxes_usd: float = 5.60,
) -> list[RedemptionOption]:
    """Generate all redemption options (N) for a flight.

    For a flight operated by `operating_airline`, finds every loyalty program
    that can book it (own-metal + alliance partners + special partners) and
    returns the chart-based rates for each.

    Args:
        operating_airline: canonical key of the airline flying the plane
        cabin: "economy", "business", or "first"
        route_region: from classify_route() — "domestic", "transatlantic", etc.
        cash_price_usd: cash price for cents-per-mile calculation
        taxes_usd: estimated taxes/fees for award bookings

    Returns:
        List of RedemptionOption sorted by miles_required ascending.
    """
    op_key = normalize_airline(operating_airline)
    bookable = get_bookable_programs(op_key)

    options: list[RedemptionOption] = []
    for prog_key in bookable:
        chart = PROGRAMS.get(prog_key)
        if not chart:
            continue

        rate = chart.get_rate(route_region, cabin)
        if not rate:
            continue

        # Determine booking type
        if prog_key == op_key:
            booking_type = "own_metal"
        elif any(op_key in partners for partners in [SPECIAL_PARTNERS.get(prog_key, [])]):
            booking_type = "special_partner"
        else:
            booking_type = "partner"

        # Partner surcharge
        miles_low = rate.miles_low
        miles_high = rate.miles_high
        if booking_type != "own_metal" and chart.partner_surcharge_pct > 0:
            miles_low = int(miles_low * (1 + chart.partner_surcharge_pct / 100))
            miles_high = int(miles_high * (1 + chart.partner_surcharge_pct / 100))

        # Cents per mile value
        cpp = round(cash_price_usd / miles_low * 100, 1) if miles_low > 0 and cash_price_usd > 0 else 0.0

        transfers = get_transfer_sources(prog_key)

        options.append(RedemptionOption(
            program_name=chart.program_name,
            program_airline=prog_key,
            miles_required=miles_low,
            miles_high=miles_high,
            taxes_usd=taxes_usd,
            booking_type=booking_type,
            is_dynamic=rate.is_dynamic,
            is_estimate=True,
            transfer_partners=transfers,
            cents_per_mile=cpp,
            notes=rate.notes,
        ))

    # Sort by miles required (best value first)
    options.sort(key=lambda o: o.miles_required)
    return options


def compute_cents_per_mile(cash_price: float, miles: int) -> float:
    """Calculate cents per mile value: (cash_price / miles) * 100."""
    if miles <= 0:
        return 0.0
    return round(cash_price / miles * 100, 2)
