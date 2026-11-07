"""
pse_quant/api/rate_limiting/token_bucket.py — Multi-Tier Token Bucket Algorithm
=============================================================================
Institutional-grade, thread-safe implementation of the Token Bucket rate limiting
algorithm. Solves the boundary-burst vulnerability of fixed-window counters and
enforces multi-tier quota governance (Anonymous, Free, Paid, Admin).
"""

from __future__ import annotations
import math
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class ClientTier(str, Enum):
    """Client quota tiers determining burst capacity and refill rate."""
    ANONYMOUS = "anonymous"
    FREE = "free"
    PAID = "paid"
    ADMIN = "admin"


@dataclass(frozen=True)
class QuotaConfig:
    """
    Capacity and refill parameters for a rate limit bucket.
    - capacity: Maximum burst tokens available in the bucket.
    - refill_rate_per_sec: Tokens continuously added back per second.
    """
    capacity: float
    refill_rate_per_sec: float

    @property
    def sustained_per_minute(self) -> float:
        """Equivalent sustained requests permitted per minute."""
        return self.refill_rate_per_sec * 60.0


# Tier Quota Presets
TIER_QUOTAS: dict[ClientTier, QuotaConfig] = {
    # Unauthenticated visitors: 20 burst, 30 req/min sustained
    ClientTier.ANONYMOUS: QuotaConfig(capacity=20.0, refill_rate_per_sec=0.5),
    # Registered free users: 60 burst, 60 req/min sustained
    ClientTier.FREE: QuotaConfig(capacity=60.0, refill_rate_per_sec=1.0),
    # Paying customers (PWYC ₱49+ or Monthly): 300 burst, 300 req/min sustained
    ClientTier.PAID: QuotaConfig(capacity=300.0, refill_rate_per_sec=5.0),
    # Administrators / internal automated services: 1000 burst, 3000 req/min sustained
    ClientTier.ADMIN: QuotaConfig(capacity=1000.0, refill_rate_per_sec=50.0),
}


@dataclass
class TokenBucketResult:
    """Evaluation result of a token consumption attempt."""
    allowed: bool
    remaining_tokens: int
    burst_capacity: int
    retry_after_seconds: float
    reset_seconds: float
    tier: ClientTier


class TokenBucket:
    """
    Thread-safe Token Bucket for a single client key.
    Calculates fractional token replenishment continuously based on timestamp differentials.
    """

    def __init__(self, capacity: float, refill_rate_per_sec: float):
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate_per_sec)
        self.tokens = float(capacity)
        self.last_refill = time.time()
        self._lock = threading.Lock()

    def consume(self, cost: float = 1.0, now: Optional[float] = None) -> Tuple[bool, float, float, float]:
        """
        Consumes tokens from the bucket.
        Returns:
            (allowed, remaining_tokens, retry_after_sec, reset_sec)
        """
        current_time = now if now is not None else time.time()

        with self._lock:
            # 1. Continuous replenishment: tokens += elapsed * refill_rate
            elapsed = max(0.0, current_time - self.last_refill)
            self.last_refill = current_time
            self.tokens = min(self.capacity, self.tokens + (elapsed * self.refill_rate))

            # 2. Consumption check
            if self.tokens >= cost:
                self.tokens -= cost
                remaining = self.tokens
                reset_sec = (self.capacity - self.tokens) / self.refill_rate if self.refill_rate > 0 else 0.0
                return True, remaining, 0.0, reset_sec
            else:
                deficit = cost - self.tokens
                retry_after = deficit / self.refill_rate if self.refill_rate > 0 else 60.0
                reset_sec = (self.capacity - self.tokens) / self.refill_rate if self.refill_rate > 0 else 60.0
                return False, self.tokens, retry_after, reset_sec


class TokenBucketStore:
    """
    In-memory registry of TokenBuckets with TTL eviction of idle client buckets.
    """

    def __init__(self, idle_ttl_seconds: float = 3600.0):
        self._buckets: dict[str, TokenBucket] = {}
        self._tier_map: dict[str, ClientTier] = {}
        self._idle_ttl = idle_ttl_seconds
        self._lock = threading.Lock()

    def get_or_create(self, client_key: str, tier: ClientTier) -> TokenBucket:
        """Retrieves existing bucket for client_key or initializes one with tier quota."""
        with self._lock:
            bucket = self._buckets.get(client_key)
            if bucket is None:
                quota = TIER_QUOTAS.get(tier, TIER_QUOTAS[ClientTier.ANONYMOUS])
                bucket = TokenBucket(capacity=quota.capacity, refill_rate_per_sec=quota.refill_rate_per_sec)
                self._buckets[client_key] = bucket
                self._tier_map[client_key] = tier
            return bucket

    def evaluate(self, client_key: str, tier: ClientTier, cost: float = 1.0, now: Optional[float] = None) -> TokenBucketResult:
        """Evaluates token consumption and returns structured result."""
        bucket = self.get_or_create(client_key, tier)
        allowed, remaining, retry_after, reset_sec = bucket.consume(cost=cost, now=now)

        return TokenBucketResult(
            allowed=allowed,
            remaining_tokens=max(0, math.floor(remaining)),
            burst_capacity=int(bucket.capacity),
            retry_after_seconds=round(retry_after, 2),
            reset_seconds=round(reset_sec, 2),
            tier=tier,
        )

    def prune_idle_buckets(self, current_time: Optional[float] = None) -> int:
        """Removes buckets that have been inactive longer than idle_ttl."""
        now = current_time if current_time is not None else time.time()
        pruned_count = 0
        with self._lock:
            keys_to_delete = [
                key for key, bucket in self._buckets.items()
                if (now - bucket.last_refill) > self._idle_ttl
            ]
            for key in keys_to_delete:
                del self._buckets[key]
                self._tier_map.pop(key, None)
                pruned_count += 1
        return pruned_count

    def clear(self) -> None:
        """Clears all stored buckets."""
        with self._lock:
            self._buckets.clear()
            self._tier_map.clear()
