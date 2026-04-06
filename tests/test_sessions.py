"""Unit tests for the session manager (no real browser launched)."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from smart_travel.accounts.sessions import SessionManager


@pytest.fixture
def mgr(tmp_path: Path) -> SessionManager:
    return SessionManager(session_dir=tmp_path / "sessions", max_age_hours=12)


class TestSessionStateFile:
    def test_has_fresh_state_false_when_no_file(self, mgr: SessionManager) -> None:
        assert mgr._has_fresh_state("nonexistent-id") is False

    def test_has_fresh_state_true_when_recent(self, mgr: SessionManager, tmp_path: Path) -> None:
        mgr._session_dir.mkdir(parents=True, exist_ok=True)
        state_file = mgr._state_path("abc123")
        state_file.write_text("{}")
        assert mgr._has_fresh_state("abc123") is True

    def test_has_fresh_state_false_when_stale(self, mgr: SessionManager) -> None:
        mgr._session_dir.mkdir(parents=True, exist_ok=True)
        state_file = mgr._state_path("stale-id")
        state_file.write_text("{}")
        # Backdate the modification time by 13 hours
        old_time = time.time() - (13 * 3600)
        import os
        os.utime(state_file, (old_time, old_time))
        assert mgr._has_fresh_state("stale-id") is False

    def test_state_path_is_unique_per_account(self, mgr: SessionManager) -> None:
        p1 = mgr._state_path("id-1")
        p2 = mgr._state_path("id-2")
        assert p1 != p2
        assert "id-1" in str(p1)
        assert "id-2" in str(p2)

    def test_invalidate_session_deletes_file(self, mgr: SessionManager) -> None:
        mgr._session_dir.mkdir(parents=True, exist_ok=True)
        state_file = mgr._state_path("del-id")
        state_file.write_text("{}")
        assert state_file.exists()

        import anyio
        anyio.run(mgr.invalidate_session, "del-id")
        assert not state_file.exists()

    def test_invalidate_session_noop_if_no_file(self, mgr: SessionManager) -> None:
        import anyio
        # Should not raise
        anyio.run(mgr.invalidate_session, "nonexistent")


class TestApplyStealth:
    @pytest.mark.anyio
    async def test_stealth_available_calls_apply(self, mgr: SessionManager) -> None:
        mock_context = AsyncMock()
        mock_stealth_instance = AsyncMock()

        # Patch _STEALTH_AVAILABLE and inject a fake _Stealth into the module
        import smart_travel.accounts.sessions as sessions_mod
        with patch.object(sessions_mod, "_STEALTH_AVAILABLE", True):
            with patch.object(sessions_mod, "_Stealth", create=True, return_value=mock_stealth_instance):
                await mgr._apply_stealth(mock_context)
                mock_stealth_instance.apply_stealth_async.assert_called_once_with(mock_context)

    @pytest.mark.anyio
    async def test_fallback_runs_when_stealth_absent(self, mgr: SessionManager) -> None:
        mock_context = AsyncMock()

        with patch("smart_travel.accounts.sessions._STEALTH_AVAILABLE", False):
            await mgr._apply_stealth(mock_context)
            mock_context.add_init_script.assert_called_once()
            script = mock_context.add_init_script.call_args[0][0]
            assert "webdriver" in script
