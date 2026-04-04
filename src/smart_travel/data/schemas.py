"""Canonical result schemas for all travel data sources.

Every source—whether API, browser scraper, or mock—normalises its
output to one of these TypedDicts so consumers see a uniform shape.
"""

from __future__ import annotations

from typing import Any, TypedDict

from typing_extensions import NotRequired


# ---------------------------------------------------------------------------
# Flights
# ---------------------------------------------------------------------------

class FlightResult(TypedDict):
    """Normalised flight search result."""

    source: str                              # "amadeus", "mock", …
    flight_number: str
    airline: str
    origin: str
    origin_airport: str
    destination: str
    destination_airport: str
    date: str
    departure_time: str
    duration: str
    stops: int
    cabin_class: str
    price_usd: NotRequired[float | None]     # Cash price (None for points-only)
    total_price_usd: NotRequired[float | None]
    passengers: int
    seats_remaining: NotRequired[int | None]
    points_price: NotRequired[int | None]    # e.g. 70 000 miles
    points_program: NotRequired[str | None]  # e.g. "united", "aeroplan"
    booking_url: NotRequired[str | None]     # Deep link


# ---------------------------------------------------------------------------
# Hotels
# ---------------------------------------------------------------------------

class HotelResult(TypedDict):
    """Normalised hotel search result."""

    source: str
    name: str
    city: str
    neighborhood: str
    star_rating: NotRequired[int | None]
    guest_rating: NotRequired[float | None]
    review_count: NotRequired[int | None]
    price_per_night_usd: float
    total_price_usd: float
    total_nights: int
    check_in: str
    check_out: str
    guests: int
    rooms: int
    amenities: list[str]
    cancellation_policy: str
    rooms_available: NotRequired[int | None]
    points_price: NotRequired[int | None]
    points_program: NotRequired[str | None]


# ---------------------------------------------------------------------------
# Events / tickets
# ---------------------------------------------------------------------------

class EventResult(TypedDict):
    """Normalised event/ticket search result."""

    source: str
    name: str
    event_type: str
    venue: str
    city: str
    date: str
    time: str
    price_range_usd: dict[str, float]
    average_price_usd: float
    tickets_available: NotRequired[int | None]
    rating: NotRequired[float | None]
    url: NotRequired[str | None]
