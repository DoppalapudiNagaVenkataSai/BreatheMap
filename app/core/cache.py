"""Two-level caching (L1 in-process LRU + L2 store)."""

import hashlib
import json
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from app.storage.base import CacheStore


class TTLCache:
    """In-process L1 LRU TTL cache."""

    def __init__(self, maxsize: int = 512) -> None:
        self.maxsize = maxsize
        self._data: OrderedDict[str, tuple[Any, float]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        if key not in self._data:
            return None
        val, expires_at = self._data[key]
        if time.monotonic() > expires_at:
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return val

    def set(self, key: str, val: Any, ttl_seconds: int) -> None:
        if key in self._data:
            del self._data[key]
        elif len(self._data) >= self.maxsize:
            self._data.popitem(last=False)
        self._data[key] = (val, time.monotonic() + ttl_seconds)

    def clear(self) -> None:
        self._data.clear()


l1_cache = TTLCache(maxsize=512)


def make_cache_key(prefix: str, payload: dict[str, Any]) -> str:
    """Generate SHA-256 cache key from stable JSON serialization."""
    serialized = json.dumps(payload, sort_keys=True)
    digest = hashlib.sha256(serialized.encode()).hexdigest()[:24]
    return f"{prefix}:{digest}"


async def get_or_set(
    cache_store: CacheStore | None,
    key: str,
    ttl_seconds: int,
    factory: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    """Retrieve from L1 then L2; compute and store if absent."""
    # L1
    val_l1 = l1_cache.get(key)
    if val_l1 is not None and isinstance(val_l1, dict):
        return val_l1

    # L2
    if cache_store:
        val_l2 = await cache_store.get(key)
        if val_l2 is not None:
            l1_cache.set(key, val_l2, ttl_seconds)
            return val_l2

    # Factory
    fresh_val = await factory()
    l1_cache.set(key, fresh_val, ttl_seconds)
    if cache_store:
        await cache_store.set(key, fresh_val, ttl_seconds)

    return fresh_val
