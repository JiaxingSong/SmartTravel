"""Abstract base classes for all travel data sources.

Every provider—API client, browser scraper, mobile endpoint, or mock
generator—is a *source*.  Sources are self-describing (via
:class:`SourceInfo`) and self-registering into the
:class:`~smart_travel.data.sources.registry.SourceRegistry`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class FetchMethod(Enum):
    """How a source obtains its data."""

    API = "api"              # httpx / REST
    BROWSER = "browser"      # Playwright automation
    MOBILE_API = "mobile"    # Reverse-engineered mobile endpoints
    MOCK = "mock"            # Fallback mock data


class PriceType(Enum):
    """What kind of pricing a source can return."""

    CASH = "cash"
    POINTS = "points"


# ---------------------------------------------------------------------------
# Self-describing metadata
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SourceInfo:
    """Metadata that describes a source's capabilities."""

    name: str                              # e.g. "amadeus", "delta_web"
    domain: str                            # "flights", "hotels", "tickets"
    fetch_method: FetchMethod
    price_types: frozenset[PriceType]      # What prices it returns
    priority: int                          # Lower = preferred (mock=999)
    airlines: frozenset[str] = field(      # IATA codes; empty = all
        default_factory=frozenset,
    )
    hotel_chains: frozenset[str] = field(  # Chain names; empty = all
        default_factory=frozenset,
    )


# ---------------------------------------------------------------------------
# Base source
# ---------------------------------------------------------------------------

class BaseSource(ABC):
    """Root abstract class for every data source."""

    info: SourceInfo

    @abstractmethod
    async def is_available(self) -> bool:
        """Return *True* when the source has the config/deps it needs."""
        ...

    async def close(self) -> None:
        """Release any held resources (HTTP clients, browsers, …)."""


# ---------------------------------------------------------------------------
# Domain-specific bases
# ---------------------------------------------------------------------------

class BaseFlightSource(BaseSource):
    """ABC for sources that return flight results."""

    @abstractmethod
    async def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None = None,
        cabin_class: str = "economy",
        passengers: int = 1,
        max_price: float | None = None,
        max_stops: int | None = None,
    ) -> list[dict[str, Any]]:
        ...


class BaseHotelSource(BaseSource):
    """ABC for sources that return hotel results."""

    @abstractmethod
    async def search_hotels(
        self,
        city: str,
        check_in: str,
        check_out: str,
        guests: int = 1,
        rooms: int = 1,
        min_stars: int | None = None,
        max_price_per_night: float | None = None,
        required_amenities: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        ...


class BaseTicketSource(BaseSource):
    """ABC for sources that return event/ticket results."""

    @abstractmethod
    async def search_tickets(
        self,
        city: str,
        date_from: str,
        date_to: str,
        event_type: str | None = None,
        max_price: float | None = None,
        min_rating: float | None = None,
    ) -> list[dict[str, Any]]:
        ...
