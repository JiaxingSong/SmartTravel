"""Cache store abstract base class and in-memory implementation.

The :class:`CacheStore` ABC defines the cache contract.
:class:`InMemoryCacheStore` is the default zero-dependency backend.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CacheEntry:
    """A single cached value with TTL tracking."""

    key: str
    domain: str
    value: Any
    created_at: float
    expires_at: float

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at


class CacheStore(ABC):
    """Abstract cache store interface."""

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """Return the cached value or ``None`` on miss / expiry."""
        ...

    @abstractmethod
    async def put(self, key: str, domain: str, value: Any, ttl: int) -> None:
        """Store *value* under *key* with a time-to-live in seconds."""
        ...

    @abstractmethod
    async def invalidate(self, key: str) -> None:
        """Remove a single cache entry."""
        ...

    @abstractmethod
    async def clear(self, domain: str | None = None) -> None:
        """Clear all entries, optionally scoped to a domain."""
        ...

    async def close(self) -> None:
        """Release resources (no-op for in-memory)."""


class InMemoryCacheStore(CacheStore):
    """In-memory cache with TTL expiration and LRU-style eviction.

    Parameters
    ----------
    max_entries:
        Maximum number of entries to keep.  When exceeded, the oldest
        entries are evicted first.
    """

    def __init__(self, max_entries: int = 500) -> None:
        self._max_entries = max_entries
        self._store: dict[str, CacheEntry] = {}

    async def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.is_expired:
            del self._store[key]
            return None
        return entry.value

    async def put(self, key: str, domain: str, value: Any, ttl: int) -> None:
        now = time.time()
        self._store[key] = CacheEntry(
            key=key,
            domain=domain,
            value=value,
            created_at=now,
            expires_at=now + ttl,
        )
        self._evict_if_needed()

    async def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    async def clear(self, domain: str | None = None) -> None:
        if domain is None:
            self._store.clear()
        else:
            to_remove = [k for k, v in self._store.items() if v.domain == domain]
            for k in to_remove:
                del self._store[k]

    def _evict_if_needed(self) -> None:
        """Remove oldest entries when store exceeds max capacity."""
        if len(self._store) <= self._max_entries:
            return
        # Purge expired first
        expired = [k for k, v in self._store.items() if v.is_expired]
        for k in expired:
            del self._store[k]
        # If still over, remove oldest by created_at
        while len(self._store) > self._max_entries:
            oldest_key = min(self._store, key=lambda k: self._store[k].created_at)
            del self._store[oldest_key]

    @property
    def size(self) -> int:
        """Number of entries currently stored (including expired)."""
        return len(self._store)
