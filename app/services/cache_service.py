"""
Simple in-memory cache with expiration (TTL) to store results of expensive operations and avoid repeated computations.
Improves performance and reduces latency, but data is lost when the application restarts.
"""

import time
from typing import Any, Optional


class SimpleTTLCache:
    def __init__(self):
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        item = self._store.get(key)

        if item is None:
            return None

        value, expires_at = item

        if time.time() > expires_at:
            self._store.pop(key, None)
            return None

        return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._store[key] = (value, time.time() + ttl_seconds)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)


cache = SimpleTTLCache()