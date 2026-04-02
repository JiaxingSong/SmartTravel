"""PostgreSQL-backed cache store.

Stores search results in the ``search_cache`` table with server-side
TTL expiration (``expires_at`` column).  Requires ``asyncpg`` and a
running PostgreSQL instance.
"""

from __future__ import annotations

import json
from typing import Any

from smart_travel.cache.store import CacheStore


class PostgresCacheStore(CacheStore):
    """Cache store backed by PostgreSQL via :mod:`smart_travel.db.pool`."""

    async def get(self, key: str) -> Any | None:
        from smart_travel.db.pool import get_pool

        pool = await get_pool()
        row = await pool.fetchrow(
            "SELECT results_json FROM search_cache "
            "WHERE key = $1 AND expires_at > NOW()",
            key,
        )
        if row is None:
            return None
        return json.loads(row["results_json"])

    async def put(self, key: str, domain: str, value: Any, ttl: int) -> None:
        from smart_travel.db.pool import get_pool

        pool = await get_pool()
        payload = json.dumps(value)
        await pool.execute(
            """
            INSERT INTO search_cache (key, domain, results_json, created_at, expires_at)
            VALUES ($1, $2, $3::jsonb, NOW(), NOW() + make_interval(secs => $4))
            ON CONFLICT (key) DO UPDATE
                SET results_json = EXCLUDED.results_json,
                    domain = EXCLUDED.domain,
                    created_at = NOW(),
                    expires_at = NOW() + make_interval(secs => $4)
            """,
            key,
            domain,
            payload,
            float(ttl),
        )

    async def invalidate(self, key: str) -> None:
        from smart_travel.db.pool import get_pool

        pool = await get_pool()
        await pool.execute("DELETE FROM search_cache WHERE key = $1", key)

    async def clear(self, domain: str | None = None) -> None:
        from smart_travel.db.pool import get_pool

        pool = await get_pool()
        if domain is None:
            await pool.execute("DELETE FROM search_cache")
        else:
            await pool.execute(
                "DELETE FROM search_cache WHERE domain = $1", domain,
            )

    async def close(self) -> None:
        # Pool lifecycle is managed by db/pool.py
        pass
