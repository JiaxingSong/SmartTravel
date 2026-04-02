"""Memory store ABC and in-memory implementation.

The :class:`MemoryStore` defines the contract for session/message
persistence and user preference management.  :class:`InMemoryMemoryStore`
is the default zero-dependency backend (resets on process restart).
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any

from smart_travel.memory.session import Message, Session
from smart_travel.memory.preferences import UserPreferences


class MemoryStore(ABC):
    """Abstract memory store for sessions and preferences."""

    # --- Sessions ---

    @abstractmethod
    async def create_session(self) -> Session:
        """Create and return a new empty session."""
        ...

    @abstractmethod
    async def load_session(self, session_id: str) -> Session | None:
        """Load a session by ID.  Returns ``None`` if not found."""
        ...

    @abstractmethod
    async def save_message(self, session_id: str, message: Message) -> None:
        """Append a message to an existing session."""
        ...

    @abstractmethod
    async def list_sessions(self, limit: int = 10) -> list[Session]:
        """List recent sessions (newest first), without messages."""
        ...

    # --- Preferences ---

    @abstractmethod
    async def get_preference(self, key: str) -> Any | None:
        """Return a single preference value or ``None``."""
        ...

    @abstractmethod
    async def set_preference(self, key: str, value: Any) -> None:
        """Set or update a user preference."""
        ...

    @abstractmethod
    async def get_all_preferences(self) -> UserPreferences:
        """Return all user preferences as a :class:`UserPreferences`."""
        ...

    async def close(self) -> None:
        """Release resources (no-op for in-memory)."""


class InMemoryMemoryStore(MemoryStore):
    """In-memory memory store.  All data is lost on restart."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._preferences: dict[str, Any] = {}

    # --- Sessions ---

    async def create_session(self) -> Session:
        session = Session(id=str(uuid.uuid4()))
        self._sessions[session.id] = session
        return session

    async def load_session(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    async def save_message(self, session_id: str, message: Message) -> None:
        session = self._sessions.get(session_id)
        if session is not None:
            session.add_message(message)

    async def list_sessions(self, limit: int = 10) -> list[Session]:
        sessions = sorted(
            self._sessions.values(),
            key=lambda s: s.updated_at,
            reverse=True,
        )
        # Return copies without messages for lightweight listing
        return [
            Session(id=s.id, created_at=s.created_at, updated_at=s.updated_at)
            for s in sessions[:limit]
        ]

    # --- Preferences ---

    async def get_preference(self, key: str) -> Any | None:
        return self._preferences.get(key)

    async def set_preference(self, key: str, value: Any) -> None:
        self._preferences[key] = value

    async def get_all_preferences(self) -> UserPreferences:
        return UserPreferences(self._preferences)
