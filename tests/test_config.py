"""Tests for smart_travel.config."""

from __future__ import annotations

import os

import pytest

from smart_travel.config import (
    AmadeusConfig,
    AppConfig,
    TicketmasterConfig,
    load_config,
)


class TestAmadeusConfig:

    def test_default_is_unconfigured(self):
        cfg = AmadeusConfig()
        assert not cfg.is_configured

    def test_with_keys_is_configured(self):
        cfg = AmadeusConfig(api_key="k", api_secret="s")
        assert cfg.is_configured

    def test_test_env_url(self):
        cfg = AmadeusConfig(environment="test")
        assert "test.api.amadeus.com" in cfg.base_url

    def test_production_env_url(self):
        cfg = AmadeusConfig(environment="production")
        assert cfg.base_url == "https://api.amadeus.com"


class TestTicketmasterConfig:

    def test_default_is_unconfigured(self):
        assert not TicketmasterConfig().is_configured

    def test_with_key(self):
        assert TicketmasterConfig(api_key="x").is_configured


class TestLoadConfig:

    def test_loads_empty_env(self, monkeypatch: pytest.MonkeyPatch):
        # Clear any existing keys and bust the lru_cache
        load_config.cache_clear()
        for var in (
            "AMADEUS_API_KEY", "AMADEUS_API_SECRET", "AMADEUS_ENVIRONMENT",
            "TICKETMASTER_API_KEY",
        ):
            monkeypatch.delenv(var, raising=False)

        cfg = load_config()
        assert not cfg.amadeus.is_configured
        assert not cfg.ticketmaster.is_configured
        load_config.cache_clear()

    def test_loads_keys_from_env(self, monkeypatch: pytest.MonkeyPatch):
        load_config.cache_clear()
        monkeypatch.setenv("AMADEUS_API_KEY", "ak")
        monkeypatch.setenv("AMADEUS_API_SECRET", "as")
        monkeypatch.setenv("TICKETMASTER_API_KEY", "tm")

        cfg = load_config()
        assert cfg.amadeus.is_configured
        assert cfg.ticketmaster.is_configured
        load_config.cache_clear()

    def test_environment_selection(self, monkeypatch: pytest.MonkeyPatch):
        load_config.cache_clear()
        monkeypatch.setenv("AMADEUS_ENVIRONMENT", "production")

        cfg = load_config()
        assert cfg.amadeus.environment == "production"
        load_config.cache_clear()
