"""Lazy asyncpg connection pool singleton.

The pool is created on first access and runs schema migrations
automatically.  Call :func:`close_pool` during shutdown to release
connections cleanly.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncpg  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Return the shared connection pool, creating it on first call.

    Reads ``POSTGRES_DSN`` via :func:`smart_travel.config.load_config`
    and runs pending migrations before returning the pool.
    """
    global _pool
    if _pool is not None:
        return _pool

    try:
        import asyncpg as _asyncpg  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "asyncpg is required for PostgreSQL support. "
            "Install it with: pip install smart-travel[postgres]"
        ) from exc

    from smart_travel.config import load_config
    config = load_config()

    if not config.postgres.is_configured:
        raise RuntimeError(
            "POSTGRES_DSN environment variable is not set. "
            "Set it or switch to in-memory backend."
        )

    _pool = await _asyncpg.create_pool(dsn=config.postgres.dsn, min_size=1, max_size=5)

    # Run migrations on first connect
    from smart_travel.db.migrations import run_migrations
    await run_migrations(_pool)

    logger.info("PostgreSQL pool created (DSN: %s...)", config.postgres.dsn[:30])
    return _pool


async def close_pool() -> None:
    """Close the shared connection pool if it exists."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL pool closed")
