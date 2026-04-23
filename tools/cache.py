from __future__ import annotations
import time
import json
from typing import Any

class TTLCache:
    """
    Thread-safe in-memory cache with optional TTL.
    ttl_seconds=None means entries never expire.
    """
    def __init__(self, ttl_seconds: int | None = None):
        self._store: dict[str, tuple[Any, float]] = {}
        self._ttl = ttl_seconds
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        if key not in self._store:
            self._misses += 1
            return None
        value, ts = self._store[key]
        if self._ttl is not None and (time.time() - ts) > self._ttl:
            del self._store[key]
            self._misses += 1
            return None
        self._hits += 1
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (value, time.time())

    def make_key(self, **kwargs) -> str:
        return json.dumps(kwargs, sort_keys=True, default=str)

    def stats(self) -> dict:
        return {"hits": self._hits, "misses": self._misses}

    def reset_stats(self) -> None:
        self._hits = 0
        self._misses = 0
