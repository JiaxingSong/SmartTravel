"""Configuration for SmartTravel data sources.

Reads API keys and settings from environment variables (with optional
python-dotenv support). Each source has its own frozen dataclass config
section with an ``is_configured`` property that checks whether the
required keys are present.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


# ---------------------------------------------------------------------------
# Per-source configs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AmadeusConfig:
    """Amadeus API credentials (flights + hotels cash prices)."""

    api_key: str = ""
    api_secret: str = ""
    environment: str = "test"  # "test" or "production"

    @property
    def base_url(self) -> str:
        if self.environment == "production":
            return "https://api.amadeus.com"
        return "https://test.api.amadeus.com"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_secret)


@dataclass(frozen=True)
class SeatsAeroConfig:
    """seats.aero Partner API credentials (flight award/points availability)."""

    api_key: str = ""
    base_url: str = "https://seats.aero/partnerapi"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


@dataclass(frozen=True)
class TicketmasterConfig:
    """Ticketmaster Discovery API credentials (event/ticket prices)."""

    api_key: str = ""
    base_url: str = "https://app.ticketmaster.com/discovery/v2"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


@dataclass(frozen=True)
class BrowserConfig:
    """Config for Playwright-based sources (V2+)."""

    headless: bool = True
    timeout_ms: int = 30000
    user_data_dir: str = ""  # Persist login sessions


@dataclass(frozen=True)
class CacheConfig:
    """Cache layer configuration."""

    backend: str = "memory"        # "memory" or "postgres"
    ttl_flights: int = 600         # 10 min
    ttl_hotels: int = 1800         # 30 min
    ttl_tickets: int = 1200        # 20 min
    max_entries: int = 500         # in-memory only


@dataclass(frozen=True)
class MemoryConfig:
    """Agent memory / session persistence configuration."""

    backend: str = "memory"        # "memory" or "postgres"


@dataclass(frozen=True)
class PostgresConfig:
    """Shared PostgreSQL connection configuration."""

    dsn: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.dsn)


# ---------------------------------------------------------------------------
# Top-level application config
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AppConfig:
    """Aggregated configuration for all data sources."""

    amadeus: AmadeusConfig = field(default_factory=AmadeusConfig)
    seats_aero: SeatsAeroConfig = field(default_factory=SeatsAeroConfig)
    ticketmaster: TicketmasterConfig = field(default_factory=TicketmasterConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    postgres: PostgresConfig = field(default_factory=PostgresConfig)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _try_load_dotenv() -> None:
    """Attempt to load a .env file if python-dotenv is installed."""
    try:
        from dotenv import load_dotenv  # type: ignore[import-untyped]
        load_dotenv()
    except ImportError:
        pass


@lru_cache(maxsize=1)
def load_config() -> AppConfig:
    """Build an :class:`AppConfig` from environment variables.

    Environment variables read:
    - ``AMADEUS_API_KEY``, ``AMADEUS_API_SECRET``, ``AMADEUS_ENVIRONMENT``
    - ``SEATS_AERO_API_KEY``
    - ``TICKETMASTER_API_KEY``
    - ``BROWSER_HEADLESS``, ``BROWSER_TIMEOUT_MS``
    - ``CACHE_BACKEND``, ``CACHE_TTL_FLIGHTS``, ``CACHE_TTL_HOTELS``,
      ``CACHE_TTL_TICKETS``, ``CACHE_MAX_ENTRIES``
    - ``MEMORY_BACKEND``
    - ``POSTGRES_DSN``
    """
    _try_load_dotenv()

    amadeus = AmadeusConfig(
        api_key=os.environ.get("AMADEUS_API_KEY", ""),
        api_secret=os.environ.get("AMADEUS_API_SECRET", ""),
        environment=os.environ.get("AMADEUS_ENVIRONMENT", "test"),
    )

    seats_aero = SeatsAeroConfig(
        api_key=os.environ.get("SEATS_AERO_API_KEY", ""),
    )

    ticketmaster = TicketmasterConfig(
        api_key=os.environ.get("TICKETMASTER_API_KEY", ""),
    )

    browser = BrowserConfig(
        headless=os.environ.get("BROWSER_HEADLESS", "true").lower() == "true",
        timeout_ms=int(os.environ.get("BROWSER_TIMEOUT_MS", "30000")),
    )

    cache = CacheConfig(
        backend=os.environ.get("CACHE_BACKEND", "memory"),
        ttl_flights=int(os.environ.get("CACHE_TTL_FLIGHTS", "600")),
        ttl_hotels=int(os.environ.get("CACHE_TTL_HOTELS", "1800")),
        ttl_tickets=int(os.environ.get("CACHE_TTL_TICKETS", "1200")),
        max_entries=int(os.environ.get("CACHE_MAX_ENTRIES", "500")),
    )

    memory = MemoryConfig(
        backend=os.environ.get("MEMORY_BACKEND", "memory"),
    )

    postgres = PostgresConfig(
        dsn=os.environ.get("POSTGRES_DSN", ""),
    )

    return AppConfig(
        amadeus=amadeus,
        seats_aero=seats_aero,
        ticketmaster=ticketmaster,
        browser=browser,
        cache=cache,
        memory=memory,
        postgres=postgres,
    )
