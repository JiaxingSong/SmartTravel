"""Database schema migrations.

Creates the four tables used by the cache and memory subsystems.
All migrations are idempotent (``IF NOT EXISTS``).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncpg  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

_MIGRATIONS: list[str] = [
    # --- Sessions ---
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id          TEXT PRIMARY KEY,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    # --- Messages ---
    """
    CREATE TABLE IF NOT EXISTS messages (
        id          SERIAL PRIMARY KEY,
        session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        role        TEXT NOT NULL,
        content     TEXT NOT NULL,
        timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_messages_session_id
        ON messages(session_id)
    """,
    # --- Preferences ---
    """
    CREATE TABLE IF NOT EXISTS preferences (
        key         TEXT PRIMARY KEY,
        value       JSONB NOT NULL,
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    # --- Search cache ---
    """
    CREATE TABLE IF NOT EXISTS search_cache (
        key          TEXT PRIMARY KEY,
        domain       TEXT NOT NULL,
        results_json JSONB NOT NULL,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        expires_at   TIMESTAMPTZ NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_search_cache_domain
        ON search_cache(domain)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_search_cache_expires
        ON search_cache(expires_at)
    """,
]


async def run_migrations(pool: asyncpg.Pool) -> None:
    """Execute all pending schema migrations.

    Each statement uses ``IF NOT EXISTS`` so it is safe to run
    repeatedly.
    """
    async with pool.acquire() as conn:
        for sql in _MIGRATIONS:
            await conn.execute(sql)
    logger.info("Database migrations completed (%d statements)", len(_MIGRATIONS))
