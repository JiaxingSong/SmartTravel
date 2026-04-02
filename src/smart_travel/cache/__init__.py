"""TTL cache layer for search results.

Provides in-memory caching by default with optional PostgreSQL persistence.
The cache sits in the resolver before source fan-out to avoid redundant
API/browser calls.
"""

from smart_travel.cache.keys import make_cache_key
from smart_travel.cache.store import CacheStore, InMemoryCacheStore

__all__ = ["CacheStore", "InMemoryCacheStore", "make_cache_key"]
