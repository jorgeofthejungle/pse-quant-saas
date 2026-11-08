"""
pse_quant/cache — Multi-Tier Cache-Aside Subsystem
==================================================
Provides thread-safe in-memory caching with single-flight dog-pile mutexes,
TTL jitter, LRU eviction, and automated invalidation hooks.
"""

from pse_quant.cache.engine import CacheEngine, CacheEntry

# Global singleton cache instance for stock profiles, rankings, and fact cards
global_cache = CacheEngine(max_entries=2000, default_ttl_seconds=300.0)

__all__ = ["CacheEngine", "CacheEntry", "global_cache"]
