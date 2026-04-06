"""Shared test fixtures for SmartTravel (browser agent version)."""
from __future__ import annotations

import pytest
from smart_travel.config import AppConfig, BrowserConfig, CacheConfig, MemoryConfig


@pytest.fixture
def app_config() -> AppConfig:
    return AppConfig(
        browser=BrowserConfig(headless=True, timeout_ms=5000),
        cache=CacheConfig(ttl=60, max_entries=10),
        memory=MemoryConfig(backend="memory"),
        monitor_check_interval=1,
    )
