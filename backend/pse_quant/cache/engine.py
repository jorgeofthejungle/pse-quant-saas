"""
pse_quant/cache/engine.py — Multi-Tier Cache-Aside Engine & Stampede Protection
=============================================================================
Thread-safe in-memory L1 cache with:
  1. Least-Recently-Used (LRU) bounded capacity eviction.
  2. TTL Jitter to prevent simultaneous cache expiration storms.
  3. Single-Flight Mutex Locking to prevent Cache Stampedes (Dog-Piling).
  4. Tag-based and glob pattern automated invalidation.
  5. Real-time observability metrics (hits, misses, hit ratio).
"""

from __future__ import annotations
import fnmatch
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("pse_quant.cache")


@dataclass
class CacheEntry:
    """A single cached object with expiration, access metadata, and invalidation tags."""
    value: Any
    expires_at: float
    created_at: float
    access_count: int = 0
    last_accessed_at: float = field(default_factory=time.time)
    tags: Set[str] = field(default_factory=set)


class CacheEngine:
    """
    Production-grade in-memory Cache-Aside engine with single-flight mutexes,
    bounded LRU eviction, and automated invalidation hooks.
    """

    def __init__(self, max_entries: int = 2000, default_ttl_seconds: float = 300.0):
        self.max_entries = max_entries
        self.default_ttl = default_ttl_seconds
        self._store: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._key_locks: Dict[str, threading.Lock] = {}
        self._key_locks_mutex = threading.Lock()

        # Telemetry metrics
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def _get_key_lock(self, key: str) -> threading.Lock:
        """Retrieves or creates a fine-grained mutex for single-flight dog-pile protection."""
        with self._key_locks_mutex:
            lock = self._key_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._key_locks[key] = lock
            return lock

    def get(self, key: str, now: Optional[float] = None) -> Any | None:
        """
        Retrieves an item from the cache.
        Returns None on cache miss or if the entry has expired.
        """
        current_time = now if now is not None else time.time()

        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None

            # Check expiration
            if current_time >= entry.expires_at:
                del self._store[key]
                self._misses += 1
                self._evictions += 1
                return None

            # Cache Hit
            entry.access_count += 1
            entry.last_accessed_at = current_time
            self._hits += 1
            return entry.value

    def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: Optional[float] = None,
        jitter_pct: float = 0.15,
        tags: Optional[List[str]] = None,
        now: Optional[float] = None,
    ) -> None:
        """
        Stores an item in the cache with bounded LRU eviction and TTL jitter.
        """
        current_time = now if now is not None else time.time()
        base_ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl

        # Calculate TTL with random jitter (+/- jitter_pct) to prevent simultaneous expiry storms
        delta = base_ttl * jitter_pct
        actual_ttl = max(1.0, base_ttl + random.uniform(-delta, delta))
        expires_at = current_time + actual_ttl

        with self._lock:
            # Enforce bounded LRU capacity
            if len(self._store) >= self.max_entries and key not in self._store:
                self._evict_lru()

            entry = CacheEntry(
                value=value,
                expires_at=expires_at,
                created_at=current_time,
                last_accessed_at=current_time,
                tags=set(tags or []),
            )
            self._store[key] = entry

    def _evict_lru(self) -> None:
        """Evicts the least recently accessed entry."""
        if not self._store:
            return
        # Find key with minimum last_accessed_at
        lru_key = min(self._store.keys(), key=lambda k: self._store[k].last_accessed_at)
        del self._store[lru_key]
        self._evictions += 1
        logger.debug(f"LRU eviction executed for key: {lru_key}")

    def get_or_compute(
        self,
        key: str,
        fetcher_fn: Callable[[], Any],
        ttl_seconds: Optional[float] = None,
        jitter_pct: float = 0.15,
        tags: Optional[List[str]] = None,
    ) -> Any:
        """
        Canonical Single-Flight Cache-Aside Implementation:
          1. Fast non-blocking check.
          2. Mutex acquisition on cache miss (only 1 thread computes, others wait).
          3. Double-check on lock acquisition.
          4. Executes fetcher_fn and writes to cache.
        """
        # 1. Fast read check
        cached_value = self.get(key)
        if cached_value is not None:
            return cached_value

        # 2. Acquire key-specific stampede lock
        key_lock = self._get_key_lock(key)
        with key_lock:
            # 3. Double-check cache (another thread may have populated it while waiting)
            cached_value = self.get(key)
            if cached_value is not None:
                return cached_value

            # 4. Single-flight computation
            logger.debug(f"Cache miss for '{key}'. Executing origin fetcher...")
            computed_value = fetcher_fn()

            # 5. Store in cache
            if computed_value is not None:
                self.set(key, computed_value, ttl_seconds=ttl_seconds, jitter_pct=jitter_pct, tags=tags)

            return computed_value

    def invalidate(self, key: str) -> bool:
        """Invalidates a single cache key."""
        with self._lock:
            if key in self._store:
                del self._store[key]
                logger.info(f"Invalidated cache key: {key}")
                return True
            return False

    def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidates all keys matching a glob pattern (e.g. 'stock:profile:*', 'stock:rankings:*').
        """
        with self._lock:
            matching_keys = [k for k in self._store.keys() if fnmatch.fnmatch(k, pattern)]
            for k in matching_keys:
                del self._store[k]
            if matching_keys:
                logger.info(f"Invalidated {len(matching_keys)} cache keys matching pattern '{pattern}'")
            return len(matching_keys)

    def invalidate_tag(self, tag: str) -> int:
        """Invalidates all cache entries carrying the specified tag."""
        with self._lock:
            matching_keys = [k for k, entry in self._store.items() if tag in entry.tags]
            for k in matching_keys:
                del self._store[k]
            if matching_keys:
                logger.info(f"Invalidated {len(matching_keys)} cache keys with tag '{tag}'")
            return len(matching_keys)

    def flush_all(self) -> int:
        """Clears all entries from the cache."""
        with self._lock:
            count = len(self._store)
            self._store.clear()
            logger.info(f"Flushed entire cache ({count} keys cleared)")
            return count

    def get_metrics(self) -> dict[str, Any]:
        """Returns observability telemetry on cache health and utilization."""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_ratio = round(self._hits / total_requests, 4) if total_requests > 0 else 0.0
            return {
                "active_entries": len(self._store),
                "max_entries": self.max_entries,
                "hits": self._hits,
                "misses": self._misses,
                "total_requests": total_requests,
                "hit_ratio": hit_ratio,
                "evictions": self._evictions,
            }

    def reset_metrics(self) -> None:
        """Resets telemetry counters."""
        with self._lock:
            self._hits = 0
            self._misses = 0
            self._evictions = 0
