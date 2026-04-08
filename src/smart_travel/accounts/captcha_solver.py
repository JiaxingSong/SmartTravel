"""FunCaptcha (Arkose Labs) solver for SmartTravel.

Wraps the anticaptchaofficial library to solve FunCaptcha challenges
encountered during Outlook.com account registration. Requires an
ANTICAPTCHA_API_KEY env var.

If the API key is not set, all solve attempts return None gracefully.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_API_KEY = os.environ.get("ANTICAPTCHA_API_KEY", "")

# Check if anticaptchaofficial is available
try:
    from anticaptchaofficial.funcaptchaproxyless import funcaptchaProxyless  # type: ignore[import-untyped]
    _SOLVER_AVAILABLE = True
except ImportError:
    _SOLVER_AVAILABLE = False


class CaptchaSolver:
    """Solves FunCaptcha (Arkose Labs) challenges via anti-captcha.com API.

    Usage:
        solver = CaptchaSolver()
        token = solver.solve_funcaptcha(
            website_url="https://signup.live.com/signup",
            public_key="B7D8911C-5CC8-A9A3-35B0-554ACEE604DA",
        )
        if token:
            # inject token into page
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or _API_KEY
        if not self._api_key:
            logger.debug(
                "ANTICAPTCHA_API_KEY not set — CAPTCHA solving disabled. "
                "Get a key from https://anti-captcha.com"
            )

    @property
    def is_available(self) -> bool:
        """True if both the library and API key are configured."""
        return _SOLVER_AVAILABLE and bool(self._api_key)

    def solve_funcaptcha(
        self,
        website_url: str,
        public_key: str,
        subdomain: str = "",
        timeout_seconds: int = 120,
    ) -> str | None:
        """Submit a FunCaptcha challenge and wait for the solution token.

        Args:
            website_url: The page URL where FunCaptcha appears.
            public_key: The Arkose Labs public key (extracted from page).
            subdomain: Optional subdomain/surl for the challenge.
            timeout_seconds: Max wait time for solution.

        Returns:
            The solution token string, or None if solving failed.
        """
        if not self.is_available:
            if not _SOLVER_AVAILABLE:
                logger.warning(
                    "anticaptchaofficial not installed. "
                    "Run: pip install anticaptchaofficial"
                )
            elif not self._api_key:
                logger.warning("ANTICAPTCHA_API_KEY not set")
            return None

        try:
            solver = funcaptchaProxyless()
            solver.set_verbose(0)
            solver.set_key(self._api_key)
            solver.set_website_url(website_url)
            solver.set_website_key(public_key)
            if subdomain:
                solver.set_js_api_domain(subdomain)

            logger.info(
                "Submitting FunCaptcha to anti-captcha (key=%s, url=%s)",
                public_key[:8] + "...",
                website_url[:50],
            )

            token = solver.solve_and_return_solution()
            if token:
                logger.info("FunCaptcha solved successfully")
                return token
            else:
                error = solver.err_string
                logger.warning("FunCaptcha solve failed: %s", error)
                return None

        except Exception:
            logger.warning("CaptchaSolver error", exc_info=True)
            return None


# Microsoft signup FunCaptcha public key (may change)
MICROSOFT_FUNCAPTCHA_KEY = "B7D8911C-5CC8-A9A3-35B0-554ACEE604DA"
MICROSOFT_FUNCAPTCHA_SURL = "https://client-api.arkoselabs.com"


def get_captcha_solver() -> CaptchaSolver:
    """Return a CaptchaSolver instance."""
    return CaptchaSolver()
