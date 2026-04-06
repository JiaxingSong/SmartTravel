"""Unit tests for browser MCP tools (no real browser launched)."""
from __future__ import annotations

import pytest
from smart_travel.tools import browser as bmod


class TestGetPendingAlerts:
    def test_returns_and_clears_alerts(self) -> None:
        bmod._pending_alerts.clear()
        bmod._pending_alerts.append("Alert A")
        bmod._pending_alerts.append("Alert B")
        alerts = bmod.get_pending_alerts()
        assert alerts == ["Alert A", "Alert B"]
        assert bmod._pending_alerts == []

    def test_empty_when_no_alerts(self) -> None:
        bmod._pending_alerts.clear()
        assert bmod.get_pending_alerts() == []


class TestMonitorPriceTool:
    def setup_method(self) -> None:
        bmod._monitors.clear()
        bmod._pending_alerts.clear()
        bmod._monitor_task_started = False

    @pytest.mark.anyio
    async def test_registers_monitor(self) -> None:
        result = await bmod.monitor_price_tool.handler({
            "label": "Tokyo flight",
            "url": "https://example.com/flight",
            "selector": ".price",
            "target_price": 500.0,
            "check_interval_minutes": 10,
        })
        text = result["content"][0]["text"]
        assert "Tokyo flight" in text
        assert "500.00" in text
        assert len(bmod._monitors) == 1

    @pytest.mark.anyio
    async def test_monitor_stores_correct_values(self) -> None:
        await bmod.monitor_price_tool.handler({
            "label": "Hotel watch",
            "url": "https://example.com/hotel",
            "selector": ".nightly-rate",
            "target_price": 200.0,
            "check_interval_minutes": 30,
        })
        job = bmod._monitors[0]
        assert job.label == "Hotel watch"
        assert job.target_price == 200.0
        assert job.check_interval_minutes == 30
        assert job.triggered is False

    @pytest.mark.anyio
    async def test_missing_url_returns_error(self) -> None:
        result = await bmod.monitor_price_tool.handler({
            "label": "test",
            "url": "",
            "selector": ".price",
            "target_price": 100.0,
        })
        text = result["content"][0]["text"]
        assert "required" in text.lower() or "url" in text.lower()


class TestWebSearchToolMissingPlaywright:
    @pytest.mark.anyio
    async def test_missing_query_returns_error(self) -> None:
        # We test the guard for empty query without needing Playwright
        result = await bmod.web_search_tool.handler({"query": ""})
        text = result["content"][0]["text"]
        assert "No query" in text or "query" in text.lower()


class TestOpenPageToolGuards:
    @pytest.mark.anyio
    async def test_missing_url_returns_error(self) -> None:
        result = await bmod.open_page_tool.handler({"url": ""})
        text = result["content"][0]["text"]
        assert "No URL" in text or "url" in text.lower()


class TestFillFormToolGuards:
    @pytest.mark.anyio
    async def test_missing_url_returns_error(self) -> None:
        result = await bmod.fill_form_tool.handler({"url": "", "fields": {}, "submit": False})
        text = result["content"][0]["text"]
        assert "No URL" in text or "url" in text.lower()


class TestCleanPageText:
    def test_collapses_blank_lines(self) -> None:
        text = "Line 1\n\n\n\n\nLine 2"
        cleaned = bmod._clean_page_text(text)
        assert "\n\n\n" not in cleaned
        assert "Line 1" in cleaned
        assert "Line 2" in cleaned

    def test_truncates_long_text(self) -> None:
        long_text = "x" * 10000
        cleaned = bmod._clean_page_text(long_text)
        assert len(cleaned) <= bmod._PAGE_TRUNCATE_LIMIT + 20
        assert "[truncated]" in cleaned

    def test_short_text_unchanged_length(self) -> None:
        text = "Short text"
        assert bmod._clean_page_text(text) == text
