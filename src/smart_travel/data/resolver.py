"""High-level search functions that the MCP tools call.

The resolver is the **single entry point** for every search.  It
orchestrates the :class:`~smart_travel.data.sources.registry.SourceRegistry`:

1. Checks the cache for a previous hit (returns immediately if found).
2. Selects available sources (with optional filters).
3. Fans out to live sources concurrently.
4. Merges cash + points results when both are present.
5. Falls back to mock if no live results arrived.
6. Stores results in cache for future lookups.
"""

from __future__ import annotations

import logging
from typing import Any

import anyio

from smart_travel.cache.keys import make_cache_key
from smart_travel.cache.store import CacheStore, InMemoryCacheStore
from smart_travel.config import AppConfig, load_config
from smart_travel.data.sources.base import BaseSource, FetchMethod, PriceType
from smart_travel.data.sources.registry import SourceRegistry

logger = logging.getLogger(__name__)

# Module-level singletons (lazy)
_registry: SourceRegistry | None = None
_cache: CacheStore | None = None


def _get_registry() -> SourceRegistry:
    global _registry
    if _registry is None:
        _registry = SourceRegistry(load_config())
    return _registry


def set_registry(registry: SourceRegistry) -> None:
    """Override the global registry (useful for tests)."""
    global _registry
    _registry = registry


def _get_cache() -> CacheStore:
    """Return the module-level cache store, creating it lazily."""
    global _cache
    if _cache is None:
        config = load_config()
        if config.cache.backend == "postgres":
            from smart_travel.cache.postgres_store import PostgresCacheStore
            _cache = PostgresCacheStore()
        else:
            _cache = InMemoryCacheStore(max_entries=config.cache.max_entries)
    return _cache


def set_cache(cache: CacheStore) -> None:
    """Override the global cache store (useful for tests)."""
    global _cache
    _cache = cache


# ---------------------------------------------------------------------------
# Flight search
# ---------------------------------------------------------------------------

async def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None = None,
    cabin_class: str = "economy",
    passengers: int = 1,
    max_price: float | None = None,
    max_stops: int | None = None,
    sources: list[str] | None = None,
    airlines: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Search flights across all available sources."""

    # --- Cache check ---
    cache = _get_cache()
    cache_key = make_cache_key(
        "flights",
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        return_date=return_date,
        cabin_class=cabin_class,
        passengers=passengers,
        max_price=max_price,
        max_stops=max_stops,
        sources=sources,
        airlines=airlines,
    )
    cached = await cache.get(cache_key)
    if cached is not None:
        logger.debug("Cache HIT for flights key=%s", cache_key[:30])
        return cached

    # --- Source fan-out ---
    registry = _get_registry()

    available = await registry.get_available(
        "flights", source_names=sources, airlines=airlines,
    )

    all_results: list[dict[str, Any]] = []
    live_sources = [s for s in available if s.info.fetch_method != FetchMethod.MOCK]
    mock_sources = [s for s in available if s.info.fetch_method == FetchMethod.MOCK]

    if live_sources:
        async with anyio.create_task_group() as tg:
            for source in live_sources:
                tg.start_soon(
                    _fetch_flights, source, all_results,
                    origin, destination, departure_date, return_date,
                    cabin_class, passengers, max_price, max_stops,
                )

    # Merge cash + points results
    merged = _merge_flight_results(all_results) if all_results else []

    # Fallback to mock
    if not merged and mock_sources:
        from smart_travel.data.sources.flights.mock import MockFlightSource
        for ms in mock_sources:
            if isinstance(ms, MockFlightSource):
                merged = await ms.search_flights(
                    origin, destination, departure_date, return_date,
                    cabin_class, passengers, max_price, max_stops,
                )
                for r in merged:
                    r["_data_quality"] = "mock"
                break

    # --- Cache store ---
    if merged:
        ttl = load_config().cache.ttl_flights
        await cache.put(cache_key, "flights", merged, ttl)

    return merged


async def _fetch_flights(
    source: BaseSource,
    collector: list[dict[str, Any]],
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None,
    cabin_class: str,
    passengers: int,
    max_price: float | None,
    max_stops: int | None,
) -> None:
    try:
        from smart_travel.data.sources.base import BaseFlightSource
        if isinstance(source, BaseFlightSource):
            results = await source.search_flights(
                origin, destination, departure_date, return_date,
                cabin_class, passengers, max_price, max_stops,
            )
            for r in results:
                r.setdefault("_data_quality", "live")
            collector.extend(results)
    except Exception:
        logger.warning(
            "Source %s failed during flight search", source.info.name,
            exc_info=True,
        )


def _merge_flight_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge cash and points results by matching (date, route).

    When a cash result and a points result share the same date + route,
    the points information is attached to the cash result.  Standalone
    points-only results are appended separately.
    """
    cash: list[dict[str, Any]] = []
    points: list[dict[str, Any]] = []

    for r in results:
        if r.get("points_price") is not None and r.get("price_usd") is None:
            points.append(r)
        else:
            cash.append(r)

    if not points:
        cash.sort(key=lambda r: r.get("price_usd") or float("inf"))
        return cash

    # Index points by (date, origin_airport, destination_airport)
    points_index: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for p in points:
        key = (p.get("date", ""), p.get("origin_airport", ""), p.get("destination_airport", ""))
        points_index.setdefault(key, []).append(p)

    matched_keys: set[tuple[str, str, str]] = set()
    for c in cash:
        key = (c.get("date", ""), c.get("origin_airport", ""), c.get("destination_airport", ""))
        if key in points_index:
            best_points = min(points_index[key], key=lambda p: p.get("points_price") or float("inf"))
            c["points_price"] = best_points.get("points_price")
            c["points_program"] = best_points.get("points_program")
            matched_keys.add(key)

    # Append unmatched points-only results
    for key, plist in points_index.items():
        if key not in matched_keys:
            cash.extend(plist)

    cash.sort(key=lambda r: r.get("price_usd") or float("inf"))
    return cash


def _merge_hotel_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge cash and points hotel results by matching (check_in, name, city).

    When a cash result and a points result share the same check-in date,
    hotel name, and city, the points information is attached to the cash
    result.  Standalone points-only results are appended separately.
    """
    cash: list[dict[str, Any]] = []
    points: list[dict[str, Any]] = []

    for r in results:
        if r.get("points_price") is not None and r.get("price_per_night_usd") is None:
            points.append(r)
        else:
            cash.append(r)

    if not points:
        cash.sort(key=lambda r: r.get("price_per_night_usd") or float("inf"))
        return cash

    # Index points by (check_in, name, city)
    points_index: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for p in points:
        key = (p.get("check_in", ""), p.get("name", ""), p.get("city", ""))
        points_index.setdefault(key, []).append(p)

    matched_keys: set[tuple[str, str, str]] = set()
    for c in cash:
        key = (c.get("check_in", ""), c.get("name", ""), c.get("city", ""))
        if key in points_index:
            best_points = min(
                points_index[key],
                key=lambda p: p.get("points_price") or float("inf"),
            )
            c["points_price"] = best_points.get("points_price")
            c["points_program"] = best_points.get("points_program")
            matched_keys.add(key)

    # Append unmatched points-only results
    for key, plist in points_index.items():
        if key not in matched_keys:
            cash.extend(plist)

    cash.sort(key=lambda r: r.get("price_per_night_usd") or float("inf"))
    return cash


# ---------------------------------------------------------------------------
# Hotel search
# ---------------------------------------------------------------------------

async def search_hotels(
    city: str,
    check_in: str,
    check_out: str,
    guests: int = 1,
    rooms: int = 1,
    min_stars: int | None = None,
    max_price_per_night: float | None = None,
    required_amenities: list[str] | None = None,
    sources: list[str] | None = None,
    hotel_chains: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Search hotels across all available sources."""

    # --- Cache check ---
    cache = _get_cache()
    cache_key = make_cache_key(
        "hotels",
        city=city,
        check_in=check_in,
        check_out=check_out,
        guests=guests,
        rooms=rooms,
        min_stars=min_stars,
        max_price_per_night=max_price_per_night,
        required_amenities=required_amenities,
        sources=sources,
        hotel_chains=hotel_chains,
    )
    cached = await cache.get(cache_key)
    if cached is not None:
        logger.debug("Cache HIT for hotels key=%s", cache_key[:30])
        return cached

    # --- Source fan-out ---
    registry = _get_registry()

    available = await registry.get_available(
        "hotels", source_names=sources, hotel_chains=hotel_chains,
    )

    all_results: list[dict[str, Any]] = []
    live_sources = [s for s in available if s.info.fetch_method != FetchMethod.MOCK]
    mock_sources = [s for s in available if s.info.fetch_method == FetchMethod.MOCK]

    if live_sources:
        async with anyio.create_task_group() as tg:
            for source in live_sources:
                tg.start_soon(
                    _fetch_hotels, source, all_results,
                    city, check_in, check_out, guests, rooms,
                    min_stars, max_price_per_night, required_amenities,
                )

    if all_results:
        merged = _merge_hotel_results(all_results)
        # --- Cache store ---
        ttl = load_config().cache.ttl_hotels
        await cache.put(cache_key, "hotels", merged, ttl)
        return merged

    # Fallback to mock
    if mock_sources:
        from smart_travel.data.sources.hotels.mock import MockHotelSource
        for ms in mock_sources:
            if isinstance(ms, MockHotelSource):
                results = await ms.search_hotels(
                    city, check_in, check_out, guests, rooms,
                    min_stars, max_price_per_night, required_amenities,
                )
                for r in results:
                    r["_data_quality"] = "mock"
                return results

    return []


async def _fetch_hotels(
    source: BaseSource,
    collector: list[dict[str, Any]],
    city: str,
    check_in: str,
    check_out: str,
    guests: int,
    rooms: int,
    min_stars: int | None,
    max_price_per_night: float | None,
    required_amenities: list[str] | None,
) -> None:
    try:
        from smart_travel.data.sources.base import BaseHotelSource
        if isinstance(source, BaseHotelSource):
            results = await source.search_hotels(
                city, check_in, check_out, guests, rooms,
                min_stars, max_price_per_night, required_amenities,
            )
            for r in results:
                r.setdefault("_data_quality", "live")
            collector.extend(results)
    except Exception:
        logger.warning(
            "Source %s failed during hotel search", source.info.name,
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Ticket search
# ---------------------------------------------------------------------------

async def search_tickets(
    city: str,
    date_from: str,
    date_to: str,
    event_type: str | None = None,
    max_price: float | None = None,
    min_rating: float | None = None,
    sources: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Search tickets across all available sources."""

    # --- Cache check ---
    cache = _get_cache()
    cache_key = make_cache_key(
        "tickets",
        city=city,
        date_from=date_from,
        date_to=date_to,
        event_type=event_type,
        max_price=max_price,
        min_rating=min_rating,
        sources=sources,
    )
    cached = await cache.get(cache_key)
    if cached is not None:
        logger.debug("Cache HIT for tickets key=%s", cache_key[:30])
        return cached

    # --- Source fan-out ---
    registry = _get_registry()

    available = await registry.get_available(
        "tickets", source_names=sources,
    )

    all_results: list[dict[str, Any]] = []
    live_sources = [s for s in available if s.info.fetch_method != FetchMethod.MOCK]
    mock_sources = [s for s in available if s.info.fetch_method == FetchMethod.MOCK]

    if live_sources:
        async with anyio.create_task_group() as tg:
            for source in live_sources:
                tg.start_soon(
                    _fetch_tickets, source, all_results,
                    city, date_from, date_to, event_type,
                    max_price, min_rating,
                )

    if all_results:
        all_results.sort(key=lambda r: (r.get("date", ""), r.get("time", "")))
        # --- Cache store ---
        ttl = load_config().cache.ttl_tickets
        await cache.put(cache_key, "tickets", all_results, ttl)
        return all_results

    # Fallback to mock
    if mock_sources:
        from smart_travel.data.sources.tickets.mock import MockTicketSource
        for ms in mock_sources:
            if isinstance(ms, MockTicketSource):
                results = await ms.search_tickets(
                    city, date_from, date_to, event_type,
                    max_price, min_rating,
                )
                for r in results:
                    r["_data_quality"] = "mock"
                return results

    return []


async def _fetch_tickets(
    source: BaseSource,
    collector: list[dict[str, Any]],
    city: str,
    date_from: str,
    date_to: str,
    event_type: str | None,
    max_price: float | None,
    min_rating: float | None,
) -> None:
    try:
        from smart_travel.data.sources.base import BaseTicketSource
        if isinstance(source, BaseTicketSource):
            results = await source.search_tickets(
                city, date_from, date_to, event_type,
                max_price, min_rating,
            )
            for r in results:
                r.setdefault("_data_quality", "live")
            collector.extend(results)
    except Exception:
        logger.warning(
            "Source %s failed during ticket search", source.info.name,
            exc_info=True,
        )
