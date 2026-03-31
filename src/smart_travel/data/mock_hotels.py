"""Realistic mock hotel data and search functionality.

Swap this module for a real API client (e.g., Booking.com, Expedia) by
implementing the same `search_hotels` interface.
"""

from __future__ import annotations

import random
from typing import Any


HOTEL_CHAINS = [
    "Marriott", "Hilton", "Hyatt", "IHG", "Wyndham",
    "Best Western", "Accor", "Radisson", "Four Seasons", "Ritz-Carlton",
    "Sheraton", "Westin", "W Hotels", "St. Regis", "Fairmont",
    "Mandarin Oriental", "Peninsula", "Aman", "Park Hyatt", "Conrad",
]

BOUTIQUE_NAMES = [
    "The Azure", "Maison Lumiere", "Hotel Indigo", "The Nomad",
    "Ace Hotel", "Soho House", "The Standard", "Freehand",
    "citizenM", "YOTEL", "Pod Hotel", "The Line",
    "Graduate Hotel", "Moxy", "Canopy by Hilton", "Aloft",
]

ALL_AMENITIES = [
    "wifi", "pool", "gym", "spa", "restaurant", "bar",
    "room_service", "parking", "airport_shuttle", "business_center",
    "pet_friendly", "laundry", "concierge", "breakfast_included",
    "ocean_view", "balcony", "kitchen", "ev_charging",
]

# Base nightly rates by city (standard room, mid-range)
_CITY_BASE_RATES: dict[str, int] = {
    "Seattle": 180, "New York": 280, "Los Angeles": 220,
    "San Francisco": 250, "Chicago": 190, "Tokyo": 200,
    "London": 260, "Paris": 270, "Dubai": 300,
    "Singapore": 230, "Sydney": 240, "Toronto": 170,
    "Frankfurt": 160, "Hong Kong": 250, "Bangkok": 80,
    "Seoul": 150, "Mumbai": 90, "Rome": 180,
    "Amsterdam": 200, "Denver": 160, "Miami": 210,
    "Dallas": 150, "Atlanta": 140, "Boston": 220,
    "Honolulu": 280,
}

STAR_MULTIPLIERS = {
    2: 0.5,
    3: 0.75,
    4: 1.0,
    5: 2.0,
}


def _generate_hotels(
    city: str,
    check_in: str,
    check_out: str,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """Generate a set of realistic hotels for a given city."""
    rng = random.Random(seed if seed is not None else hash((city, check_in)))

    base_rate = _CITY_BASE_RATES.get(city, 160)
    hotels: list[dict[str, Any]] = []
    num_hotels = rng.randint(8, 16)

    for i in range(num_hotels):
        stars = rng.choices([2, 3, 4, 5], weights=[10, 30, 40, 20])[0]
        star_mult = STAR_MULTIPLIERS[stars]

        # Pick name
        if stars >= 4 and rng.random() < 0.6:
            name = f"{rng.choice(HOTEL_CHAINS)} {city}"
        else:
            name = f"{rng.choice(BOUTIQUE_NAMES)} {city}"

        price_variation = rng.uniform(0.7, 1.5)
        price_per_night = round(base_rate * star_mult * price_variation, 2)

        # Amenities: higher star hotels have more
        num_amenities = min(len(ALL_AMENITIES), stars * 2 + rng.randint(0, 3))
        # Always include wifi for 3+ stars
        amenities_pool = list(ALL_AMENITIES)
        rng.shuffle(amenities_pool)
        amenities = amenities_pool[:num_amenities]
        if stars >= 3 and "wifi" not in amenities:
            amenities.append("wifi")
        amenities.sort()

        rating = round(min(5.0, max(1.0, stars - 0.5 + rng.uniform(-0.3, 0.8))), 1)
        review_count = rng.randint(50, 5000)

        neighborhoods = {
            "Tokyo": ["Shinjuku", "Shibuya", "Ginza", "Roppongi", "Asakusa", "Akihabara"],
            "New York": ["Midtown", "SoHo", "Chelsea", "Upper East Side", "Times Square", "Brooklyn"],
            "London": ["Westminster", "Kensington", "Soho", "Shoreditch", "Mayfair", "Camden"],
            "Paris": ["Le Marais", "Montmartre", "Saint-Germain", "Champs-Elysees", "Bastille"],
            "Seattle": ["Downtown", "Capitol Hill", "Belltown", "Pioneer Square", "South Lake Union"],
        }
        city_neighborhoods = neighborhoods.get(city, ["Downtown", "City Center", "Old Town"])
        neighborhood = rng.choice(city_neighborhoods)

        hotels.append({
            "name": name,
            "city": city,
            "neighborhood": neighborhood,
            "star_rating": stars,
            "guest_rating": rating,
            "review_count": review_count,
            "price_per_night_usd": price_per_night,
            "check_in": check_in,
            "check_out": check_out,
            "amenities": amenities,
            "cancellation_policy": rng.choice([
                "Free cancellation until 24h before check-in",
                "Free cancellation until 48h before check-in",
                "Non-refundable",
                "Free cancellation until 7 days before check-in",
            ]),
            "rooms_available": rng.randint(1, 15),
        })

    hotels.sort(key=lambda h: h["price_per_night_usd"])
    return hotels


def search_hotels(
    city: str,
    check_in: str,
    check_out: str,
    guests: int = 1,
    rooms: int = 1,
    min_stars: int | None = None,
    max_price_per_night: float | None = None,
    required_amenities: list[str] | None = None,
    seed: int | None = 42,
) -> list[dict[str, Any]]:
    """Search for hotels matching the given criteria.

    Args:
        city: City name (e.g., "Tokyo").
        check_in: Check-in date in YYYY-MM-DD format.
        check_out: Check-out date in YYYY-MM-DD format.
        guests: Number of guests.
        rooms: Number of rooms needed.
        min_stars: Minimum star rating (2-5).
        max_price_per_night: Maximum nightly rate in USD.
        required_amenities: List of required amenities (e.g., ["pool", "wifi"]).
        seed: Random seed for reproducible results.

    Returns:
        List of hotel dictionaries matching the criteria.
    """
    hotels = _generate_hotels(city, check_in, check_out, seed)

    if min_stars is not None:
        hotels = [h for h in hotels if h["star_rating"] >= min_stars]

    if max_price_per_night is not None:
        hotels = [h for h in hotels if h["price_per_night_usd"] <= max_price_per_night]

    if required_amenities:
        required_set = {a.lower() for a in required_amenities}
        hotels = [h for h in hotels if required_set.issubset(set(h["amenities"]))]

    # Annotate with total cost
    for h in hotels:
        h["guests"] = guests
        h["rooms"] = rooms
        # Simple night count from date strings
        try:
            d_in = _parse_date(check_in)
            d_out = _parse_date(check_out)
            nights = max(1, (d_out - d_in).days)
        except (ValueError, TypeError):
            nights = 1
        h["total_nights"] = nights
        h["total_price_usd"] = round(h["price_per_night_usd"] * nights * rooms, 2)

    return hotels


def _parse_date(date_str: str):
    """Parse a YYYY-MM-DD date string."""
    from datetime import datetime
    return datetime.strptime(date_str, "%Y-%m-%d")
