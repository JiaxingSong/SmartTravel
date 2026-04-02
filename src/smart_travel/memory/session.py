"""Session and message dataclasses for conversation persistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Message:
    """A single chat message."""

    role: str                          # "user" or "assistant"
    content: str
    timestamp: datetime = field(default_factory=_utcnow)


@dataclass
class Session:
    """A conversation session containing a sequence of messages."""

    id: str
    messages: list[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def add_message(self, message: Message) -> None:
        """Append a message and update the session timestamp."""
        self.messages.append(message)
        self.updated_at = _utcnow()
