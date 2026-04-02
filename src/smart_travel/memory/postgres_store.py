"""PostgreSQL-backed memory store.

Persists sessions, messages, and user preferences across process restarts.
Requires ``asyncpg`` and a running PostgreSQL instance.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from smart_travel.memory.preferences import UserPreferences
from smart_travel.memory.session import Message, Session
from smart_travel.memory.store import MemoryStore


class PostgresMemoryStore(MemoryStore):
    """Memory store backed by PostgreSQL via :mod:`smart_travel.db.pool`."""

    # --- Sessions ---

    async def create_session(self) -> Session:
        from smart_travel.db.pool import get_pool

        pool = await get_pool()
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        await pool.execute(
            "INSERT INTO sessions (id, created_at, updated_at) VALUES ($1, $2, $3)",
            session_id, now, now,
        )
        return Session(id=session_id, created_at=now, updated_at=now)

    async def load_session(self, session_id: str) -> Session | None:
        from smart_travel.db.pool import get_pool

        pool = await get_pool()
        row = await pool.fetchrow(
            "SELECT id, created_at, updated_at FROM sessions WHERE id = $1",
            session_id,
        )
        if row is None:
            return None

        messages_rows = await pool.fetch(
            "SELECT role, content, timestamp FROM messages "
            "WHERE session_id = $1 ORDER BY id",
            session_id,
        )
        messages = [
            Message(
                role=r["role"],
                content=r["content"],
                timestamp=r["timestamp"].replace(tzinfo=timezone.utc),
            )
            for r in messages_rows
        ]
        return Session(
            id=row["id"],
            messages=messages,
            created_at=row["created_at"].replace(tzinfo=timezone.utc),
            updated_at=row["updated_at"].replace(tzinfo=timezone.utc),
        )

    async def save_message(self, session_id: str, message: Message) -> None:
        from smart_travel.db.pool import get_pool

        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO messages (session_id, role, content, timestamp) "
                    "VALUES ($1, $2, $3, $4)",
                    session_id, message.role, message.content, message.timestamp,
                )
                await conn.execute(
                    "UPDATE sessions SET updated_at = $1 WHERE id = $2",
                    message.timestamp, session_id,
                )

    async def list_sessions(self, limit: int = 10) -> list[Session]:
        from smart_travel.db.pool import get_pool

        pool = await get_pool()
        rows = await pool.fetch(
            "SELECT id, created_at, updated_at FROM sessions "
            "ORDER BY updated_at DESC LIMIT $1",
            limit,
        )
        return [
            Session(
                id=r["id"],
                created_at=r["created_at"].replace(tzinfo=timezone.utc),
                updated_at=r["updated_at"].replace(tzinfo=timezone.utc),
            )
            for r in rows
        ]

    # --- Preferences ---

    async def get_preference(self, key: str) -> Any | None:
        from smart_travel.db.pool import get_pool

        pool = await get_pool()
        row = await pool.fetchrow(
            "SELECT value FROM preferences WHERE key = $1", key,
        )
        if row is None:
            return None
        return json.loads(row["value"])

    async def set_preference(self, key: str, value: Any) -> None:
        from smart_travel.db.pool import get_pool

        pool = await get_pool()
        payload = json.dumps(value)
        await pool.execute(
            """
            INSERT INTO preferences (key, value, updated_at)
            VALUES ($1, $2::jsonb, NOW())
            ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value,
                    updated_at = NOW()
            """,
            key, payload,
        )

    async def get_all_preferences(self) -> UserPreferences:
        from smart_travel.db.pool import get_pool

        pool = await get_pool()
        rows = await pool.fetch("SELECT key, value FROM preferences")
        data = {r["key"]: json.loads(r["value"]) for r in rows}
        return UserPreferences(data)

    async def close(self) -> None:
        # Pool lifecycle is managed by db/pool.py
        pass
