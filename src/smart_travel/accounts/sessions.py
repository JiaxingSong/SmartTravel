"""Authenticated browser session management for SmartTravel award search.

Manages persistent Playwright browser contexts with:
- storage_state persistence (cookies + localStorage) per account
- playwright-stealth injection to mask headless detection
- Human-like interaction helpers (random delays, character-by-character typing)
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from pathlib import Path
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page

from smart_travel.accounts.store import LoyaltyAccount, get_account_store

logger = logging.getLogger(__name__)

# Realistic User-Agent (mirrors browser.py)
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# Minimal stealth init script used when playwright-stealth is not installed
_MINIMAL_STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
"""

# Check playwright-stealth availability once at import time
try:
    from playwright_stealth import Stealth as _Stealth  # type: ignore[import-untyped]
    _STEALTH_AVAILABLE = True
except ImportError:
    _STEALTH_AVAILABLE = False
    logger.debug(
        "playwright-stealth not installed — using minimal stealth fallback. "
        "Run: pip install playwright-stealth"
    )


# ---------------------------------------------------------------------------
# Human-like interaction helpers
# ---------------------------------------------------------------------------

async def _human_delay(min_ms: int = 500, max_ms: int = 2000) -> None:
    """Sleep a random amount to mimic human reaction time."""
    await asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


async def _type_humanlike(page: "Page", selector: str, text: str) -> None:
    """Click a field and type text character-by-character with timing jitter."""
    await page.click(selector)
    await asyncio.sleep(random.uniform(0.1, 0.3))
    # Clear existing value
    await page.evaluate(
        f'(() => {{ const el = document.querySelector("{selector}"); '
        f'if (el) el.value = ""; }})()'
    )
    for char in text:
        await page.keyboard.type(char)
        await asyncio.sleep(random.uniform(0.04, 0.14))


# ---------------------------------------------------------------------------
# Session Manager
# ---------------------------------------------------------------------------

class SessionManager:
    """Manages authenticated Playwright browser contexts per loyalty account.

    Each account's session is persisted as a Playwright storage_state JSON
    file (cookies + localStorage). Saved sessions are reused for up to
    SESSION_MAX_AGE_HOURS before forcing a fresh login.
    """

    def __init__(self, session_dir: Path | None = None, max_age_hours: int | None = None) -> None:
        if session_dir is None:
            session_dir = Path(os.environ.get("SESSION_DIR", ".smart_travel_sessions"))
        if max_age_hours is None:
            max_age_hours = int(os.environ.get("SESSION_MAX_AGE_HOURS", "12"))
        self._session_dir = session_dir
        self._max_age_hours = max_age_hours
        self._session_dir.mkdir(parents=True, exist_ok=True)

    def _state_path(self, account_id: str) -> Path:
        return self._session_dir / f"{account_id}.json"

    def _has_fresh_state(self, account_id: str) -> bool:
        """Return True if a saved session exists and is within max_age_hours."""
        p = self._state_path(account_id)
        if not p.exists():
            return False
        age_hours = (time.time() - p.stat().st_mtime) / 3600
        return age_hours < self._max_age_hours

    async def _apply_stealth(self, context: "BrowserContext") -> None:
        """Inject stealth scripts into a browser context."""
        if _STEALTH_AVAILABLE:
            stealth = _Stealth()
            await stealth.apply_stealth_async(context)
        else:
            await context.add_init_script(_MINIMAL_STEALTH_SCRIPT)

    async def get_authenticated_page(
        self,
        account: LoyaltyAccount,
        login_fn: Callable[["Page", LoyaltyAccount], Awaitable[bool]],
        verify_fn: Callable[["Page"], Awaitable[bool]],
    ) -> tuple["Browser", "BrowserContext", "Page"] | None:
        """Return an authenticated (browser, context, page) for the account.

        Strategy:
        1. If fresh saved state exists, load it and verify login via verify_fn.
        2. If verify fails or no saved state, perform fresh login via login_fn.
        3. On success: persist storage_state to disk, reset failure counter.
        4. On failure: mark account as failed, close browser, return None.

        The caller owns the returned (browser, context, page) and must call
        await browser.close() in a finally: block.
        """
        from smart_travel.config import load_config

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright is not installed")
            return None

        config = load_config()
        pw = await async_playwright().start()

        try:
            browser = await pw.chromium.launch(
                headless=config.browser.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )

            context_kwargs: dict = {
                "user_agent": _USER_AGENT,
                "locale": "en-US",
                "timezone_id": "America/Los_Angeles",
                "viewport": {"width": 1280, "height": 800},
            }
            state_path = self._state_path(account.account_id)
            use_saved = self._has_fresh_state(account.account_id)
            if use_saved:
                context_kwargs["storage_state"] = str(state_path)

            context = await browser.new_context(**context_kwargs)
            await self._apply_stealth(context)
            page = await context.new_page()
            page.set_default_timeout(config.browser.timeout_ms)

            # If we loaded saved state, verify the session is still live
            if use_saved:
                try:
                    if await verify_fn(page):
                        return browser, context, page
                    logger.debug("Saved session for %s expired, re-logging in", account.account_id)
                except Exception:
                    logger.debug("Session verify failed for %s", account.account_id, exc_info=True)

            # Perform fresh login
            try:
                success = await login_fn(page, account)
            except Exception:
                logger.warning("Login raised exception for %s", account.account_id, exc_info=True)
                success = False

            if success:
                await context.storage_state(path=str(state_path))
                get_account_store().reset_failures(account.account_id)
                return browser, context, page
            else:
                get_account_store().mark_failed(account.account_id)
                await browser.close()
                await pw.stop()
                return None

        except Exception:
            logger.warning("get_authenticated_page failed", exc_info=True)
            try:
                await pw.stop()
            except Exception:
                pass
            return None

    async def invalidate_session(self, account_id: str) -> None:
        """Delete saved session state, forcing re-login on next use."""
        p = self._state_path(account_id)
        if p.exists():
            p.unlink()
            logger.debug("Invalidated session for account %s", account_id)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    """Return the shared SessionManager singleton."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
