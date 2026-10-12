"""LRU Cache for idempotent/read-only tool calls and schema queries."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheEntry:
    value: str
    expires_at: float


class ToolOutputCache:
    """In-memory LRU and TTL cache for tool executions.

    Automatically caches read-like tool invocations (get, list, read, search, find, describe)
    or explicitly declared idempotent calls to eliminate duplicate child-process runs.
    """

    # Verbs that typically signify side-effect-free, deterministic read operations
    READ_VERBS = ("get", "list", "read", "search", "find", "describe", "show", "inspect", "query", "select")
    WRITE_VERBS = ("create", "add", "insert", "update", "delete", "remove", "drop", "post", "put", "patch", "execute", "run", "write")

    def __init__(self, max_entries: int = 128, default_ttl: float = 300.0):
        self.max_entries = max_entries
        self.default_ttl = default_ttl
        self._cache: dict[str, CacheEntry] = {}
        self.hits = 0
        self.misses = 0

    def is_cacheable(self, tool_name: str) -> bool:
        """Heuristically determine if a tool is safe to cache based on naming conventions."""
        name_lower = tool_name.lower()
        # Explicit write verbs take precedence
        if any(w in name_lower for w in self.WRITE_VERBS):
            return False
        # Known read verbs
        return any(r in name_lower for r in self.READ_VERBS)

    def _make_key(self, tool_name: str, arguments: dict[str, Any] | None) -> str:
        serialized = json.dumps(arguments or {}, sort_keys=True, separators=(",", ":"))
        raw = f"{tool_name}:{serialized}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, tool_name: str, arguments: dict[str, Any] | None) -> str | None:
        if not self.is_cacheable(tool_name):
            return None

        key = self._make_key(tool_name, arguments)
        entry = self._cache.get(key)
        if not entry:
            self.misses += 1
            return None

        now = time.time()
        if now > entry.expires_at:
            del self._cache[key]
            self.misses += 1
            return None

        self.hits += 1
        return entry.value

    def set(self, tool_name: str, arguments: dict[str, Any] | None, value: str, ttl: float | None = None) -> None:
        if not self.is_cacheable(tool_name):
            return

        key = self._make_key(tool_name, arguments)
        now = time.time()
        expires_at = now + (ttl if ttl is not None else self.default_ttl)

        if len(self._cache) >= self.max_entries:
            # Evict expired or oldest entry
            oldest_key = min(self._cache, key=lambda k: self._cache[k].expires_at)
            del self._cache[oldest_key]

        self._cache[key] = CacheEntry(value=value, expires_at=expires_at)

    def invalidate(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
