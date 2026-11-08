"""
pse_quant/telemetry/tracker.py — High-Performance Latency Percentile & Trace Buffer
PSE Quant SaaS (v2 Rebuild) — Lab 10

Maintains in-memory rolling reservoirs for latency percentiles (p50, p95, p99)
and a circular trace buffer for distributed observability.
"""

from __future__ import annotations
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional


def _percentile(sorted_samples: List[float], p: float) -> float:
    """Calculates the p-th percentile from pre-sorted samples."""
    if not sorted_samples:
        return 0.0
    idx = int((len(sorted_samples) - 1) * (p / 100.0))
    return round(sorted_samples[idx], 2)


class RouteLatencyBucket:
    """Bounded circular reservoir tracking latencies for a specific route pattern."""

    def __init__(self, max_samples: int = 1000):
        self.max_samples = max_samples
        self.samples: deque[float] = deque(maxlen=max_samples)
        self.total_count = 0
        self.total_sum = 0.0
        self.min_ms = float("inf")
        self.max_ms = 0.0

    def add(self, duration_ms: float) -> None:
        self.samples.append(duration_ms)
        self.total_count += 1
        self.total_sum += duration_ms
        if duration_ms < self.min_ms:
            self.min_ms = duration_ms
        if duration_ms > self.max_ms:
            self.max_ms = duration_ms

    def get_stats(self) -> Dict[str, Any]:
        if not self.samples:
            return {
                "count": 0,
                "p50_ms": 0.0,
                "p95_ms": 0.0,
                "p99_ms": 0.0,
                "avg_ms": 0.0,
                "min_ms": 0.0,
                "max_ms": 0.0,
            }

        sorted_vals = sorted(self.samples)
        return {
            "count": self.total_count,
            "sample_window_size": len(self.samples),
            "p50_ms": _percentile(sorted_vals, 50.0),
            "p95_ms": _percentile(sorted_vals, 95.0),
            "p99_ms": _percentile(sorted_vals, 99.0),
            "avg_ms": round(self.total_sum / self.total_count, 2) if self.total_count > 0 else 0.0,
            "min_ms": round(self.min_ms, 2) if self.min_ms != float("inf") else 0.0,
            "max_ms": round(self.max_ms, 2),
        }


class LatencyTracker:
    """
    Central thread-safe telemetry store tracking route latencies, percentiles,
    and recent sampled trace events.
    """

    def __init__(self, max_traces: int = 200, max_samples_per_route: int = 1000):
        self._routes: Dict[str, RouteLatencyBucket] = {}
        self._recent_traces: deque[Dict[str, Any]] = deque(maxlen=max_traces)
        self._max_samples_per_route = max_samples_per_route
        self._lock = threading.Lock()

    def record_request(
        self,
        method: str,
        path: str,
        duration_ms: float,
        status_code: int,
        correlation_id: str,
    ) -> None:
        """Records a completed request's latency and appends to recent trace buffer."""
        key = f"{method.upper()} {path}"
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._lock:
            if key not in self._routes:
                self._routes[key] = RouteLatencyBucket(max_samples=self._max_samples_per_route)
            self._routes[key].add(duration_ms)

            # Circular trace log
            self._recent_traces.appendleft({
                "correlation_id": correlation_id,
                "method": method.upper(),
                "path": path,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 2),
                "timestamp": now_iso,
            })

    def get_summary(self) -> Dict[str, Any]:
        """Returns latency statistics aggregated by route and overall system."""
        with self._lock:
            routes_data = {k: v.get_stats() for k, v in sorted(self._routes.items())}

            # Overall aggregate
            all_samples: List[float] = []
            total_reqs = 0
            for bucket in self._routes.values():
                all_samples.extend(bucket.samples)
                total_reqs += bucket.total_count

            if all_samples:
                sorted_all = sorted(all_samples)
                overall = {
                    "total_requests": total_reqs,
                    "p50_ms": _percentile(sorted_all, 50.0),
                    "p95_ms": _percentile(sorted_all, 95.0),
                    "p99_ms": _percentile(sorted_all, 99.0),
                    "avg_ms": round(sum(all_samples) / len(all_samples), 2),
                    "min_ms": round(min(all_samples), 2),
                    "max_ms": round(max(all_samples), 2),
                }
            else:
                overall = {
                    "total_requests": 0,
                    "p50_ms": 0.0,
                    "p95_ms": 0.0,
                    "p99_ms": 0.0,
                    "avg_ms": 0.0,
                    "min_ms": 0.0,
                    "max_ms": 0.0,
                }

            return {
                "overall": overall,
                "routes": routes_data,
            }

    def get_recent_traces(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns the most recent sampled request traces."""
        with self._lock:
            return list(self._recent_traces)[:limit]

    def reset(self) -> None:
        """Clears all latency reservoirs and trace history."""
        with self._lock:
            self._routes.clear()
            self._recent_traces.clear()


# Global singleton instance
global_latency_tracker = LatencyTracker()
