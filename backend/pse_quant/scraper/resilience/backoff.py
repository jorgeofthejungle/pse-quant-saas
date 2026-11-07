"""
pse_quant/scraper/resilience/backoff.py — Exponential Backoff with Full Jitter
=============================================================================
Decorrelates retry timing to eliminate the 'thundering herd' problem against
PSE Edge and other external endpoints during upstream recovery.
"""

from __future__ import annotations
import random
from typing import Optional, Callable


def calculate_jittered_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter_strategy: str = "full",
    rng: Optional[Callable[[], float]] = None,
) -> float:
    """
    Calculates exponential backoff delay with random jitter (AWS Architecture pattern).

    Args:
        attempt: Zero-based retry attempt count (0, 1, 2, ...).
        base_delay: Initial retry backoff in seconds (e.g. 1.0s).
        max_delay: Upper cap on retry backoff in seconds (e.g. 30.0s).
        jitter_strategy:
            - 'full': Uniform random between 0 and min(max_delay, base * 2^attempt).
                      Recommended for maximum throughput decorrelation.
            - 'equal': Half guaranteed exponential + half random jitter.
            - 'decorrelated': Multiplicative random walk between base and 3 * prev.
        rng: Optional random generator function returning float [0.0, 1.0) for deterministic unit testing.

    Returns:
        float: Backoff sleep time in seconds.
    """
    random_val = rng() if rng is not None else random.random()
    exponential_cap = min(max_delay, base_delay * (2 ** max(0, attempt)))

    if jitter_strategy == "equal":
        # Equal jitter: half deterministic, half randomized
        half = exponential_cap / 2.0
        return round(half + (random_val * half), 3)

    # Full Jitter (Default AWS Pattern):
    # sleep = rand(0, min(max_delay, base * 2^attempt))
    return round(random_val * exponential_cap, 3)
