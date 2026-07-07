"""Thread-safe, size-aware, TTL cache — the entire storage layer.

Per the spec: no Redis, no database, no cost. A single in-process dictionary
with LRU eviction and a byte budget. Cache keys are hashes of the request
parameters, so identical requests are served instantly and, importantly,
*deduplicated* — two users asking for the same region/date share one NASA task.
"""
from __future__ import annotations

import sys
import threading
import time
from collections import OrderedDict
from typing import Any, Callable

from .config_bridge import config


class TTLCache:
    def __init__(self, max_bytes: int = config.CACHE_MAX_BYTES):
        self._store: OrderedDict[str, dict] = OrderedDict()
        self._lock = threading.RLock()
        self.max_bytes = max_bytes
        self.current_bytes = 0
        self.hits = 0
        self.misses = 0

    # -- internals ---------------------------------------------------------
    @staticmethod
    def _sizeof(value: Any) -> int:
        try:
            return sys.getsizeof(value)
        except TypeError:
            return 1024

    def _evict_if_needed(self) -> None:
        while self.current_bytes > self.max_bytes and self._store:
            _, victim = self._store.popitem(last=False)  # least-recently-used
            self.current_bytes -= victim["size"]

    def _expired(self, entry: dict) -> bool:
        return entry["expires_at"] is not None and time.time() > entry["expires_at"]

    # -- public API --------------------------------------------------------
    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None
            if self._expired(entry):
                self.current_bytes -= entry["size"]
                del self._store[key]
                self.misses += 1
                return None
            self._store.move_to_end(key)  # mark as recently used
            self.hits += 1
            return entry["value"]

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        with self._lock:
            size = self._sizeof(value)
            if key in self._store:
                self.current_bytes -= self._store[key]["size"]
            self._store[key] = {
                "value": value,
                "size": size,
                "expires_at": (time.time() + ttl) if ttl else None,
            }
            self._store.move_to_end(key)
            self.current_bytes += size
            self._evict_if_needed()

    def get_or_set(self, key: str, factory: Callable[[], Any], ttl: int | None = None) -> Any:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = factory()
        self.set(key, value, ttl)
        return value

    def update(self, key: str, **changes) -> None:
        """Mutate a cached dict value in place (used for task progress)."""
        with self._lock:
            entry = self._store.get(key)
            if entry and isinstance(entry["value"], dict):
                entry["value"].update(changes)

    def delete(self, key: str) -> None:
        with self._lock:
            entry = self._store.pop(key, None)
            if entry:
                self.current_bytes -= entry["size"]

    def stats(self) -> dict:
        with self._lock:
            total = self.hits + self.misses
            return {
                "entries": len(self._store),
                "bytes": self.current_bytes,
                "max_bytes": self.max_bytes,
                "utilisation_pct": round(100 * self.current_bytes / self.max_bytes, 1),
                "hit_rate_pct": round(100 * self.hits / total, 1) if total else 0.0,
                "hits": self.hits,
                "misses": self.misses,
            }


cache = TTLCache()
