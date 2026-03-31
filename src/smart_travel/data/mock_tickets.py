"""Realistic mock event/ticket data and search functionality.

Swap this module for a real API client (e.g., SerpAPI, Ticketmaster) by
implementing the same `search_tickets` interface.
"""

from __future__ import annotations

import random
from typing import Any


EVENT_DATA: dict[str, dict[str, list[str]]] = {
    "concert": {
        "artists": [
            "Taylor Swift", "Ed Sheeran", "Beyonce", "Coldplay",
            "The Weeknd", "Adele", "Bruno Mars", "Lady Gaga",
            "Drake", "Billie Eilish", "Harry Styles", "Dua Lipa",
            "Bad Bunny", "Kendrick Lamar", "SZA", "Post Malone",
        ],
        "venues_suffix": ["Arena", "Stadium", "Concert Hall", "Amphitheater", "Music Center"],
    },
    "sports": {
        "events": [
            "NBA Basketball", "NFL Football", "MLB Baseball", "NHL Hockey",
            "Premier League Soccer", "UFC Fight Night", "Tennis Open",
            "Formula 1 Grand Prix", "FIFA World Cup Qualifier",
            "Champions League", "Rugby World Cup", "Cricket T20",
        ],
        "venues_suffix": ["Stadium", "Arena", "Sports Center", "Field", "Park"],
    },
    "theater": {
        "shows": [
            "Hamilton", "The Lion King", "Wicked", "Les Miserables",
            "Phantom of the Opera", "Chicago", "Dear Evan Hansen",
            "Moulin Rouge", "Hadestown", "The Book of Mormon",
            "Come From Away", "Beetlejuice", "Aladdin", "Frozen",
        ],
        "venues_suffix": ["Theater", "Playhouse", "Arts Center", "Opera House", "Performing Arts Center"],
    },
    "museum": {
        "exhibitions": [
            "Modern Art Retrospective", "Ancient Egypt Exhibition",
            "Impressionist Masters", "Space & Science Discovery",
            "Photography Through the Ages", "Contemporary Sculpture",
            "Digital Art Immersive Experience", "Natural History Showcase",
            "Renaissance Art Collection", "Pop Art Exhibition",
            "Climate & Nature Gallery", "World Cultures Festival",
        ],
        "venues_suffix": ["Museum", "Gallery", "Exhibition Center", "Cultural Center", "Institute"],
    },
}

VENUE_PREFIXES: dict[str, list[str]] = {
    "Tokyo": ["Tokyo", "Nippon", "Shibuya", "Shinjuku"],
    "New York": ["Madison Square", "Broadway", "Manhattan", "Brooklyn"],
    "London": ["Royal", "West End", "Wembley", "O2"],
    "Paris": ["Grand", "Palais", "Moulin", "Bastille"],
    "Seattle": ["Seattle", "Pacific", "Emerald", "Key"],
    "Los Angeles": ["Hollywood", "Staples", "Crypto.com", "LA"],
    "Chicago": ["United", "Chicago", "Soldier", "Wrigley"],
    "Dubai": ["Dubai", "Emirates", "Palm", "Burj"],
    "Singapore": ["Marina Bay", "Esplanade", "Singapore", "Gardens"],
    "Sydney": ["Sydney", "Harbor", "Olympic", "Royal"],
}


def _generate_events(
    city: str,
    event_type: str | None,
    date_from: str,
    date_to: str,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """Generate realistic events for a city and date range."""
    rng = random.Random(seed if seed is not None else hash((city, date_from)))

    types_to_generate = [event_type] if event_type else list(EVENT_DATA.keys())
    prefixes = VENUE_PREFIXES.get(city, [city])

    events: list[dict[str, Any]] = []

    # Parse date range
    from datetime import datetime, timedelta
    try:
        d_from = datetime.strptime(date_from, "%Y-%m-%d")
        d_to = datetime.strptime(date_to, "%Y-%m-%d")
    except (ValueError, TypeError):
        d_from = datetime(2026, 4, 1)
        d_to = d_from + timedelta(days=7)

    total_days = max(1, (d_to - d_from).days)

    for etype in types_to_generate:
        edata = EVENT_DATA.get(etype, {})
        num_events = rng.randint(3, 8)

        for i in range(num_events):
            # Event name
            if etype == "concert":
                name = f"{rng.choice(edata['artists'])} Live in Concert"
            elif etype == "sports":
                name = rng.choice(edata["events"])
            elif etype == "theater":
                name = rng.choice(edata["shows"])
            elif etype == "museum":
                name = rng.choice(edata["exhibitions"])
            else:
                name = f"{etype.title()} Event"

            # Venue
            prefix = rng.choice(prefixes)
            suffix = rng.choice(edata.get("venues_suffix", ["Center"]))
            venue = f"{prefix} {suffix}"

            # Date within range
            event_day = d_from + timedelta(days=rng.randint(0, total_days))
            event_date = event_day.strftime("%Y-%m-%d")

            # Time
            if etype == "museum":
                hour = rng.choice([10, 11, 12, 13, 14])
            else:
                hour = rng.choice([18, 19, 20, 21])
            minute = rng.choice([0, 30])
            event_time = f"{hour:02d}:{minute:02d}"

            # Pricing
            if etype == "concert":
                base = rng.randint(60, 350)
            elif etype == "sports":
                base = rng.randint(40, 250)
            elif etype == "theater":
                base = rng.randint(50, 200)
            else:  # museum
                base = rng.randint(15, 45)

            price_min = round(base * 0.7, 2)
            price_max = round(base * 1.8, 2)

            events.append({
                "name": name,
                "event_type": etype,
                "venue": venue,
                "city": city,
                "date": event_date,
                "time": event_time,
                "price_range_usd": {"min": price_min, "max": price_max},
                "average_price_usd": round((price_min + price_max) / 2, 2),
                "tickets_available": rng.randint(2, 500),
                "rating": round(rng.uniform(3.5, 5.0), 1),
            })

    events.sort(key=lambda e: (e["date"], e["time"]))
    return events


def search_tickets(
    city: str,
    date_from: str,
    date_to: str,
    event_type: str | None = None,
    max_price: float | None = None,
    min_rating: float | None = None,
    seed: int | None = 42,
) -> list[dict[str, Any]]:
    """Search for event tickets matching the given criteria.

    Args:
        city: City name (e.g., "Tokyo").
        date_from: Start date in YYYY-MM-DD format.
        date_to: End date in YYYY-MM-DD format.
        event_type: Filter by type: "concert", "sports", "theater", "museum", or None for all.
        max_price: Maximum average ticket price in USD.
        min_rating: Minimum event rating (1.0-5.0).
        seed: Random seed for reproducible results.

    Returns:
        List of event dictionaries matching the criteria.
    """
    events = _generate_events(city, event_type, date_from, date_to, seed)

    if max_price is not None:
        events = [e for e in events if e["average_price_usd"] <= max_price]

    if min_rating is not None:
        events = [e for e in events if e["rating"] >= min_rating]

    return events
