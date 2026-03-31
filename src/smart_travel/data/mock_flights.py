"""Realistic mock flight data and search functionality.

Swap this module for a real API client (e.g., Amadeus) by implementing
the same `search_flights` interface.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any


AIRLINES = [
    "United Airlines", "Delta Air Lines", "American Airlines",
    "Alaska Airlines", "JetBlue Airways", "Southwest Airlines",
    "Air Canada", "British Airways", "Lufthansa", "Emirates",
    "Singapore Airlines", "ANA (All Nippon Airways)", "Japan Airlines",
    "Cathay Pacific", "Korean Air", "Turkish Airlines",
    "Air France", "KLM Royal Dutch Airlines", "Qantas",
]

AIRPORTS: dict[str, list[str]] = {
    "Seattle": ["SEA"],
    "New York": ["JFK", "EWR", "LGA"],
    "Los Angeles": ["LAX"],
    "San Francisco": ["SFO"],
    "Chicago": ["ORD", "MDW"],
    "Tokyo": ["NRT", "HND"],
    "London": ["LHR", "LGW"],
    "Paris": ["CDG", "ORY"],
    "Dubai": ["DXB"],
    "Singapore": ["SIN"],
    "Sydney": ["SYD"],
    "Toronto": ["YYZ"],
    "Frankfurt": ["FRA"],
    "Hong Kong": ["HKG"],
    "Bangkok": ["BKK"],
    "Seoul": ["ICN"],
    "Mumbai": ["BOM"],
    "Rome": ["FCO"],
    "Amsterdam": ["AMS"],
    "Denver": ["DEN"],
    "Miami": ["MIA"],
    "Dallas": ["DFW"],
    "Atlanta": ["ATL"],
    "Boston": ["BOS"],
    "Honolulu": ["HNL"],
}

# Base one-way prices (economy) between city pairs; keyed by sorted tuple
_BASE_PRICES: dict[tuple[str, str], int] = {
    ("Los Angeles", "New York"): 250,
    ("New York", "Seattle"): 280,
    ("Los Angeles", "Seattle"): 150,
    ("Chicago", "New York"): 180,
    ("London", "New York"): 450,
    ("London", "Paris"): 120,
    ("Seattle", "Tokyo"): 650,
    ("Los Angeles", "Tokyo"): 600,
    ("New York", "Tokyo"): 700,
    ("New York", "Paris"): 480,
    ("Dubai", "London"): 500,
    ("Dubai", "New York"): 750,
    ("San Francisco", "Tokyo"): 620,
    ("Honolulu", "Seattle"): 350,
    ("Honolulu", "Los Angeles"): 300,
    ("New York", "Singapore"): 800,
    ("London", "Singapore"): 550,
    ("London", "Sydney"): 900,
    ("Los Angeles", "Sydney"): 850,
    ("Bangkok", "Tokyo"): 300,
    ("Hong Kong", "Tokyo"): 280,
    ("Seoul", "Tokyo"): 200,
    ("Mumbai", "Singapore"): 250,
    ("Amsterdam", "New York"): 460,
    ("Frankfurt", "New York"): 470,
    ("Miami", "New York"): 180,
    ("Atlanta", "New York"): 160,
    ("Boston", "New York"): 120,
    ("Dallas", "New York"): 220,
    ("Denver", "Seattle"): 200,
}

CLASS_MULTIPLIERS = {
    "economy": 1.0,
    "premium_economy": 1.6,
    "business": 3.0,
    "first": 5.5,
}


def _get_base_price(city_a: str, city_b: str) -> int:
    """Get or generate a base price for a city pair."""
    key = tuple(sorted([city_a, city_b]))
    if key in _BASE_PRICES:
        return _BASE_PRICES[key]  # type: ignore[return-value]
    # Generate a plausible price based on name hashing for consistency
    h = hash(key) % 600 + 200
    return h


def _generate_flights(
    origin: str,
    destination: str,
    date: str,
    cabin_class: str = "economy",
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """Generate a set of realistic flights for a given route and date."""
    rng = random.Random(seed if seed is not None else hash((origin, destination, date)))

    base_price = _get_base_price(origin, destination)
    class_mult = CLASS_MULTIPLIERS.get(cabin_class, 1.0)

    origin_airports = AIRPORTS.get(origin, [origin[:3].upper()])
    dest_airports = AIRPORTS.get(destination, [destination[:3].upper()])

    flights: list[dict[str, Any]] = []
    num_flights = rng.randint(4, 10)

    for i in range(num_flights):
        airline = rng.choice(AIRLINES)
        stops = rng.choices([0, 1, 2], weights=[50, 35, 15])[0]

        # Price varies by airline, time of day, stops
        price_variation = rng.uniform(0.75, 1.45)
        stop_discount = 1.0 - (stops * 0.12)  # Non-stops are more expensive
        price = round(base_price * class_mult * price_variation * stop_discount, 2)

        dep_hour = rng.randint(5, 22)
        dep_min = rng.choice([0, 15, 30, 45])
        base_duration_h = max(1, int(base_price / 120))  # Rough correlation
        duration_h = base_duration_h + stops * rng.randint(1, 3)
        duration_m = rng.choice([0, 10, 20, 30, 40, 50])

        dep_airport = rng.choice(origin_airports)
        arr_airport = rng.choice(dest_airports)

        flight_num = f"{airline[:2].upper()}{rng.randint(100, 9999)}"

        flights.append({
            "flight_number": flight_num,
            "airline": airline,
            "origin": origin,
            "origin_airport": dep_airport,
            "destination": destination,
            "destination_airport": arr_airport,
            "date": date,
            "departure_time": f"{dep_hour:02d}:{dep_min:02d}",
            "duration": f"{duration_h}h {duration_m}m",
            "stops": stops,
            "cabin_class": cabin_class,
            "price_usd": price,
            "seats_remaining": rng.randint(1, 42),
        })

    flights.sort(key=lambda f: f["price_usd"])
    return flights


def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None = None,
    cabin_class: str = "economy",
    passengers: int = 1,
    max_price: float | None = None,
    max_stops: int | None = None,
    seed: int | None = 42,
) -> list[dict[str, Any]]:
    """Search for flights matching the given criteria.

    Args:
        origin: Departure city name (e.g., "Seattle").
        destination: Arrival city name (e.g., "Tokyo").
        departure_date: Date string in YYYY-MM-DD format.
        return_date: Optional return date for round-trip searches.
        cabin_class: One of economy, premium_economy, business, first.
        passengers: Number of passengers (prices are per-person).
        max_price: Maximum price per person in USD.
        max_stops: Maximum number of stops (0 = non-stop only).
        seed: Random seed for reproducible results.

    Returns:
        List of flight dictionaries matching the criteria.
    """
    flights = _generate_flights(origin, destination, departure_date, cabin_class, seed)

    # Apply filters
    if max_price is not None:
        flights = [f for f in flights if f["price_usd"] <= max_price]

    if max_stops is not None:
        flights = [f for f in flights if f["stops"] <= max_stops]

    # Add per-person note
    for f in flights:
        f["passengers"] = passengers
        f["total_price_usd"] = round(f["price_usd"] * passengers, 2)

    # If round-trip requested, generate return flights too
    if return_date:
        return_flights = _generate_flights(
            destination, origin, return_date, cabin_class,
            seed=(seed + 1000) if seed is not None else None,
        )
        if max_price is not None:
            return_flights = [f for f in return_flights if f["price_usd"] <= max_price]
        if max_stops is not None:
            return_flights = [f for f in return_flights if f["stops"] <= max_stops]
        for f in return_flights:
            f["passengers"] = passengers
            f["total_price_usd"] = round(f["price_usd"] * passengers, 2)

        return [
            {
                "type": "round_trip",
                "outbound": flights,
                "return": return_flights,
            }
        ]

    return flights
