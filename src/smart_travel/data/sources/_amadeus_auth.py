"""Shared Amadeus OAuth 2.0 token manager.

Both :mod:`flights.amadeus` and :mod:`hotels.amadeus` share the same
credential pair, so this module provides a single
:class:`AmadeusTokenManager` that lazily acquires and caches a Bearer
token, refreshing it before expiry.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from smart_travel.config import AmadeusConfig

logger = logging.getLogger(__name__)

_TOKEN_REFRESH_BUFFER_S = 60  # refresh 60 s before expiry


@dataclass
class AmadeusTokenManager:
    """Manages Amadeus OAuth2 client-credentials tokens."""

    config: AmadeusConfig
    _client: httpx.AsyncClient = field(init=False, repr=False, default=None)  # type: ignore[assignment]
    _token: str = field(init=False, default="")
    _expires_at: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=30.0,
        )

    # ----- public API -----

    async def get_token(self) -> str:
        """Return a valid Bearer token, refreshing if necessary."""
        if not self._token or time.time() >= self._expires_at:
            await self._refresh()
        return self._token

    async def get_client(self) -> httpx.AsyncClient:
        """Return an httpx client with current auth headers set."""
        token = await self.get_token()
        self._client.headers["Authorization"] = f"Bearer {token}"
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    # ----- internals -----

    async def _refresh(self) -> None:
        """POST to /v1/security/oauth2/token for a new access token."""
        logger.debug("Refreshing Amadeus access token …")
        resp = await self._client.post(
            "/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.config.api_key,
                "client_secret": self.config.api_secret,
            },
        )
        resp.raise_for_status()
        body: dict[str, Any] = resp.json()
        self._token = body["access_token"]
        expires_in = int(body.get("expires_in", 1799))
        self._expires_at = time.time() + expires_in - _TOKEN_REFRESH_BUFFER_S
        logger.debug("Amadeus token refreshed, expires in %ds", expires_in)
