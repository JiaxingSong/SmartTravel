"""Configuration for SmartTravel.

Reads settings from environment variables (with optional python-dotenv support).

Environment variables:
- ANTHROPIC_API_KEY           (required, used by claude-agent-sdk implicitly)
- BROWSER_HEADLESS            bool, default true
- BROWSER_TIMEOUT_MS          int, default 30000
- MONITOR_CHECK_INTERVAL      int minutes, default 5
- CACHE_TTL                   int seconds, default 300
- CACHE_MAX_ENTRIES           int, default 500
- MEMORY_BACKEND              "memory" (only supported value)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass(frozen=True)
class BrowserConfig:
    """Config for Playwright browser automation."""

    headless: bool = True
    timeout_ms: int = 30000


@dataclass(frozen=True)
class CacheConfig:
    """In-memory cache configuration."""

    ttl: int = 300          # seconds
    max_entries: int = 500


@dataclass(frozen=True)
class MemoryConfig:
    """Agent memory / session persistence configuration."""

    backend: str = "memory"


@dataclass(frozen=True)
class AccountConfig:
    """Configuration for airline loyalty account storage and browser sessions."""

    store_path: str = ".smart_travel_accounts.json"
    store_key: str = ""
    session_dir: str = ".smart_travel_sessions"
    session_max_age_hours: int = 12


@dataclass(frozen=True)
class AppConfig:
    """Aggregated application configuration."""

    browser: BrowserConfig = field(default_factory=BrowserConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    account: AccountConfig = field(default_factory=AccountConfig)
    monitor_check_interval: int = 5  # minutes


def _try_load_dotenv() -> None:
    """Attempt to load a .env file if python-dotenv is installed."""
    try:
        from dotenv import load_dotenv  # type: ignore[import-untyped]
        load_dotenv()
    except ImportError:
        pass


@lru_cache(maxsize=1)
def load_config() -> AppConfig:
    """Build an :class:`AppConfig` from environment variables."""
    _try_load_dotenv()

    browser = BrowserConfig(
        headless=os.environ.get("BROWSER_HEADLESS", "true").lower() == "true",
        timeout_ms=int(os.environ.get("BROWSER_TIMEOUT_MS", "30000")),
    )

    cache = CacheConfig(
        ttl=int(os.environ.get("CACHE_TTL", "300")),
        max_entries=int(os.environ.get("CACHE_MAX_ENTRIES", "500")),
    )

    memory = MemoryConfig(
        backend=os.environ.get("MEMORY_BACKEND", "memory"),
    )

    account = AccountConfig(
        store_path=os.environ.get("ACCOUNT_STORE_PATH", ".smart_travel_accounts.json"),
        store_key=os.environ.get("ACCOUNT_STORE_KEY", ""),
        session_dir=os.environ.get("SESSION_DIR", ".smart_travel_sessions"),
        session_max_age_hours=int(os.environ.get("SESSION_MAX_AGE_HOURS", "12")),
    )

    return AppConfig(
        browser=browser,
        cache=cache,
        memory=memory,
        account=account,
        monitor_check_interval=int(os.environ.get("MONITOR_CHECK_INTERVAL", "5")),
    )
