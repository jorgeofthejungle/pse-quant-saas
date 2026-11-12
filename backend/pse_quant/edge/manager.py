"""
pse_quant/edge/manager.py — Edge Cache & POP Routing Ingress Manager
PSE Quant SaaS — Lab 18
"""

from __future__ import annotations
import threading
import logging
from typing import Optional
from pse_quant.edge.models import EdgeTelemetry

logger = logging.getLogger("pse_quant.edge.manager")


class EdgeCacheManager:
    """Thread-safe operational telemetry and surrogate-key invalidation tracker."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total_requests_evaluated = 0
        self._not_modified_304_served = 0
        self._cache_miss_200_served = 0
        self._etags_generated = 0
        self._purged_tags_count = 0
        self._last_purged_tag: Optional[str] = None
        self._active_pops: dict[str, int] = {}

    def record_304(self, pop: str) -> None:
        with self._lock:
            self._total_requests_evaluated += 1
            self._not_modified_304_served += 1
            self._active_pops[pop] = self._active_pops.get(pop, 0) + 1

    def record_200(self, pop: str) -> None:
        with self._lock:
            self._total_requests_evaluated += 1
            self._cache_miss_200_served += 1
            self._active_pops[pop] = self._active_pops.get(pop, 0) + 1

    def record_etag(self) -> None:
        with self._lock:
            self._etags_generated += 1

    def purge_tags(self, tags: list[str]) -> int:
        """Simulates / registers an edge surrogate tag cache invalidation."""
        with self._lock:
            count = len(tags)
            self._purged_tags_count += count
            if tags:
                self._last_purged_tag = tags[-1]
            logger.info(f"Edge cache tags purged: {tags}")
            return count

    def get_telemetry(self) -> EdgeTelemetry:
        with self._lock:
            return EdgeTelemetry(
                total_requests_evaluated=self._total_requests_evaluated,
                not_modified_304_served=self._not_modified_304_served,
                cache_miss_200_served=self._cache_miss_200_served,
                etags_generated=self._etags_generated,
                purged_tags_count=self._purged_tags_count,
                last_purged_tag=self._last_purged_tag,
                active_pops=dict(self._active_pops),
            )

    def reset(self) -> None:
        with self._lock:
            self._total_requests_evaluated = 0
            self._not_modified_304_served = 0
            self._cache_miss_200_served = 0
            self._etags_generated = 0
            self._purged_tags_count = 0
            self._last_purged_tag = None
            self._active_pops.clear()


# Global Singleton Manager
edge_cache_manager = EdgeCacheManager()
