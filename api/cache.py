from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Any

LIVE_QUOTES_TTL_SECONDS = 5 * 60
ANALYSIS_TTL_SECONDS = 60 * 60


@dataclass(slots=True)
class CacheEntry:
    value: Any
    expires_at: float


class TTLCache:
    """Simple in-memory TTL cache backed by a dictionary."""

    def __init__(self) -> None:
        self._entries: dict[str, CacheEntry] = {}
        self._lock = Lock()

    def get(self, key: str) -> Any | None:
        now = time.time()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._entries.pop(key, None)
                return None
            return entry.value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero")

        expires_at = time.time() + ttl_seconds
        with self._lock:
            self._entries[key] = CacheEntry(value=value, expires_at=expires_at)

    def delete(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


live_quote_cache = TTLCache()
analysis_cache = TTLCache()
