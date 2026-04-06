"""Tests for the simplified AppConfig and load_config."""
from __future__ import annotations

import pytest
from smart_travel.config import AppConfig, BrowserConfig, CacheConfig, MemoryConfig, load_config


class TestAppConfig:
    def test_defaults(self) -> None:
        cfg = AppConfig()
        assert cfg.browser.headless is True
        assert cfg.browser.timeout_ms == 30000
        assert cfg.cache.ttl == 300
        assert cfg.cache.max_entries == 500
        assert cfg.memory.backend == "memory"
        assert cfg.monitor_check_interval == 5

    def test_custom_values(self) -> None:
        cfg = AppConfig(
            browser=BrowserConfig(headless=False, timeout_ms=10000),
            cache=CacheConfig(ttl=60, max_entries=100),
            memory=MemoryConfig(backend="memory"),
            monitor_check_interval=15,
        )
        assert cfg.browser.headless is False
        assert cfg.browser.timeout_ms == 10000
        assert cfg.cache.ttl == 60
        assert cfg.monitor_check_interval == 15


class TestLoadConfig:
    def test_loads_defaults(self) -> None:
        load_config.cache_clear()
        cfg = load_config()
        assert isinstance(cfg, AppConfig)
        load_config.cache_clear()

    def test_loads_browser_headless_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        load_config.cache_clear()
        monkeypatch.setenv("BROWSER_HEADLESS", "false")
        cfg = load_config()
        assert cfg.browser.headless is False
        load_config.cache_clear()

    def test_loads_browser_timeout_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        load_config.cache_clear()
        monkeypatch.setenv("BROWSER_TIMEOUT_MS", "15000")
        cfg = load_config()
        assert cfg.browser.timeout_ms == 15000
        load_config.cache_clear()

    def test_loads_cache_ttl_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        load_config.cache_clear()
        monkeypatch.setenv("CACHE_TTL", "120")
        cfg = load_config()
        assert cfg.cache.ttl == 120
        load_config.cache_clear()

    def test_loads_monitor_interval_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        load_config.cache_clear()
        monkeypatch.setenv("MONITOR_CHECK_INTERVAL", "15")
        cfg = load_config()
        assert cfg.monitor_check_interval == 15
        load_config.cache_clear()

    def test_no_api_key_fields(self) -> None:
        load_config.cache_clear()
        cfg = load_config()
        assert not hasattr(cfg, "amadeus")
        assert not hasattr(cfg, "ticketmaster")
        assert not hasattr(cfg, "postgres")
        load_config.cache_clear()
