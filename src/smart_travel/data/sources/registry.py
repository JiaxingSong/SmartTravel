"""Source registry — discovers, manages, and routes to data sources.

The :class:`SourceRegistry` is the central switchboard.  It holds all
registered sources, answers availability queries, and provides filtered
lists sorted by priority.
"""

from __future__ import annotations

import logging
from typing import Any

from smart_travel.config import AppConfig
from smart_travel.data.sources.base import (
    BaseSource,
    FetchMethod,
    PriceType,
    SourceInfo,
)

logger = logging.getLogger(__name__)


class SourceRegistry:
    """Manages all registered travel data sources."""

    def __init__(self, config: AppConfig) -> None:
        self._sources: dict[str, list[BaseSource]] = {
            "flights": [],
            "hotels": [],
            "tickets": [],
        }
        self._register_builtins(config)

    # ----- registration -----

    def _register_builtins(self, config: AppConfig) -> None:
        """Auto-register all built-in sources."""
        # Flights — API sources
        from smart_travel.data.sources.flights.amadeus import AmadeusFlightSource
        from smart_travel.data.sources.flights.seats_aero import SeatsAeroFlightSource
        from smart_travel.data.sources.flights.mock import MockFlightSource

        self._register(AmadeusFlightSource(config.amadeus))
        self._register(SeatsAeroFlightSource(config.seats_aero))

        # Flights — Browser source (optional, requires playwright)
        try:
            from smart_travel.data.sources.flights.google_flights import GoogleFlightsSource
            self._register(GoogleFlightsSource(config.browser))
        except ImportError:
            pass

        self._register(MockFlightSource())

        # Hotels — API sources
        from smart_travel.data.sources.hotels.amadeus import AmadeusHotelSource
        from smart_travel.data.sources.hotels.mock import MockHotelSource

        self._register(AmadeusHotelSource(config.amadeus))

        # Hotels — Browser source (optional, requires playwright)
        try:
            from smart_travel.data.sources.hotels.google_hotels import GoogleHotelsSource
            self._register(GoogleHotelsSource(config.browser))
        except ImportError:
            pass

        self._register(MockHotelSource())

        # Tickets
        from smart_travel.data.sources.tickets.ticketmaster import TicketmasterSource
        from smart_travel.data.sources.tickets.mock import MockTicketSource

        self._register(TicketmasterSource(config.ticketmaster))
        self._register(MockTicketSource())

    def _register(self, source: BaseSource) -> None:
        domain = source.info.domain
        if domain not in self._sources:
            self._sources[domain] = []
        self._sources[domain].append(source)

    def register(self, source: BaseSource) -> None:
        """Public API for plugins / V2+ sources to register themselves."""
        self._register(source)

    # ----- queries -----

    async def get_available(
        self,
        domain: str,
        source_names: list[str] | None = None,
        airlines: list[str] | None = None,
        hotel_chains: list[str] | None = None,
        price_types: set[PriceType] | None = None,
    ) -> list[BaseSource]:
        """Return available sources for *domain*, filtered and priority-sorted.

        Parameters
        ----------
        domain:
            ``"flights"``, ``"hotels"``, or ``"tickets"``.
        source_names:
            Restrict to these source names (e.g. ``["amadeus"]``).
        airlines:
            Only sources whose ``airlines`` set intersects (or is empty = all).
        hotel_chains:
            Only sources whose ``hotel_chains`` set intersects (or is empty).
        price_types:
            Only sources whose ``price_types`` intersect.
        """
        sources = self._sources.get(domain, [])
        result: list[BaseSource] = []

        for s in sources:
            if not await s.is_available():
                continue
            if source_names and s.info.name not in source_names:
                continue
            if airlines and s.info.airlines and not (s.info.airlines & set(airlines)):
                continue
            if hotel_chains and s.info.hotel_chains and not (s.info.hotel_chains & set(hotel_chains)):
                continue
            if price_types and not (s.info.price_types & price_types):
                continue
            result.append(s)

        result.sort(key=lambda s: s.info.priority)
        return result

    def list_sources(self, domain: str | None = None) -> list[SourceInfo]:
        """List metadata for all registered sources, optionally filtered."""
        infos: list[SourceInfo] = []
        domains = [domain] if domain else list(self._sources.keys())
        for d in domains:
            for s in self._sources.get(d, []):
                infos.append(s.info)
        return infos

    async def close_all(self) -> None:
        """Shutdown every registered source cleanly."""
        for sources in self._sources.values():
            for s in sources:
                try:
                    await s.close()
                except Exception:
                    logger.debug("Error closing source %s", s.info.name, exc_info=True)
