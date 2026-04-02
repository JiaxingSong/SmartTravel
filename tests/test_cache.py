"""Tests for the cache layer (keys + in-memory store)."""

from __future__ import annotations

import asyncio
import time

import pytest

from smart_travel.cache.keys import make_cache_key
from smart_travel.cache.store import CacheEntry, InMemoryCacheStore


# ---------------------------------------------------------------------------
# make_cache_key
# ---------------------------------------------------------------------------

class TestMakeCacheKey:

    def test_basic_key(self):
        key = make_cache_key("flights", origin="SEA", destination="NRT")
        assert key.startswith("flights:")
        assert len(key) > len("flights:") + 10  # SHA-256 hex

    def test_deterministic(self):
        k1 = make_cache_key("flights", origin="SEA", destination="NRT")
        k2 = make_cache_key("flights", origin="SEA", destination="NRT")
        assert k1 == k2

    def test_order_independent(self):
        k1 = make_cache_key("flights", origin="SEA", destination="NRT")
        k2 = make_cache_key("flights", destination="NRT", origin="SEA")
        assert k1 == k2

    def test_none_values_stripped(self):
        k1 = make_cache_key("flights", origin="SEA", max_price=None)
        k2 = make_cache_key("flights", origin="SEA")
        assert k1 == k2

    def test_case_insensitive_strings(self):
        k1 = make_cache_key("flights", origin="SEA")
        k2 = make_cache_key("flights", origin="sea")
        assert k1 == k2

    def test_different_domains(self):
        k1 = make_cache_key("flights", origin="SEA")
        k2 = make_cache_key("hotels", origin="SEA")
        assert k1 != k2

    def test_different_params(self):
        k1 = make_cache_key("flights", origin="SEA")
        k2 = make_cache_key("flights", origin="LAX")
        assert k1 != k2

    def test_list_params_sorted(self):
        k1 = make_cache_key("flights", airlines=["UA", "DL"])
        k2 = make_cache_key("flights", airlines=["DL", "UA"])
        assert k1 == k2


# ---------------------------------------------------------------------------
# CacheEntry
# ---------------------------------------------------------------------------

class TestCacheEntry:

    def test_not_expired(self):
        entry = CacheEntry("k", "d", "v", time.time(), time.time() + 3600)
        assert not entry.is_expired

    def test_expired(self):
        entry = CacheEntry("k", "d", "v", time.time() - 100, time.time() - 1)
        assert entry.is_expired


# ---------------------------------------------------------------------------
# InMemoryCacheStore
# ---------------------------------------------------------------------------

class TestInMemoryCacheStore:

    @pytest.mark.anyio
    async def test_put_and_get(self):
        store = InMemoryCacheStore()
        await store.put("key1", "flights", {"data": 1}, ttl=60)
        result = await store.get("key1")
        assert result == {"data": 1}

    @pytest.mark.anyio
    async def test_miss_returns_none(self):
        store = InMemoryCacheStore()
        assert await store.get("nonexistent") is None

    @pytest.mark.anyio
    async def test_expired_returns_none(self):
        store = InMemoryCacheStore()
        await store.put("key1", "flights", {"data": 1}, ttl=0)
        # TTL=0 means it expires immediately (at creation time)
        # sleep briefly to ensure time has passed
        await asyncio.sleep(0.01)
        assert await store.get("key1") is None

    @pytest.mark.anyio
    async def test_invalidate(self):
        store = InMemoryCacheStore()
        await store.put("key1", "flights", "val", ttl=60)
        await store.invalidate("key1")
        assert await store.get("key1") is None

    @pytest.mark.anyio
    async def test_clear_all(self):
        store = InMemoryCacheStore()
        await store.put("k1", "flights", "v1", ttl=60)
        await store.put("k2", "hotels", "v2", ttl=60)
        await store.clear()
        assert store.size == 0

    @pytest.mark.anyio
    async def test_clear_by_domain(self):
        store = InMemoryCacheStore()
        await store.put("k1", "flights", "v1", ttl=60)
        await store.put("k2", "hotels", "v2", ttl=60)
        await store.clear("flights")
        assert await store.get("k1") is None
        assert await store.get("k2") == "v2"

    @pytest.mark.anyio
    async def test_eviction_on_max_entries(self):
        store = InMemoryCacheStore(max_entries=3)
        for i in range(5):
            await store.put(f"k{i}", "flights", f"v{i}", ttl=60)
        assert store.size == 3
        # Most recent entries should survive
        assert await store.get("k4") == "v4"
        assert await store.get("k3") == "v3"

    @pytest.mark.anyio
    async def test_overwrite_existing_key(self):
        store = InMemoryCacheStore()
        await store.put("k1", "flights", "old", ttl=60)
        await store.put("k1", "flights", "new", ttl=60)
        assert await store.get("k1") == "new"

    @pytest.mark.anyio
    async def test_close_is_noop(self):
        store = InMemoryCacheStore()
        await store.close()  # should not raise
