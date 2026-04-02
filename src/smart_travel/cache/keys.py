"""Deterministic cache key generation.

Keys are domain-scoped SHA-256 hashes of the search parameters, ensuring
consistent hits regardless of parameter ordering.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def make_cache_key(domain: str, **params: Any) -> str:
    """Build a deterministic cache key from domain and search parameters.

    Parameters are sorted alphabetically, ``None`` values are stripped,
    and string values are lowercased before hashing.

    Returns a key in the form ``"flights:abc123def..."``.
    """
    cleaned: dict[str, Any] = {}
    for k in sorted(params.keys()):
        v = params[k]
        if v is None:
            continue
        if isinstance(v, str):
            v = v.lower().strip()
        elif isinstance(v, list):
            v = sorted(str(i).lower().strip() for i in v)
        cleaned[k] = v

    payload = json.dumps(cleaned, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return f"{domain}:{digest}"
