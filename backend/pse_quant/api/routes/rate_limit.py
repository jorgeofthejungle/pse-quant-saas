"""
pse_quant/api/routes/rate_limit.py — Rate Limiting & Quota Governance Diagnostics
================================================================================
Provides client-facing observability into quota consumption, assigned tier,
burst capacity, and mathematical replenishment parameters.
"""

from __future__ import annotations
from fastapi import APIRouter, Request

from pse_quant.api.rate_limiting.fingerprint import resolve_client_fingerprint
from pse_quant.api.rate_limiting.token_bucket import TIER_QUOTAS, ClientTier
from pse_quant.api.rate_limiting.middleware import global_token_store

router = APIRouter(prefix="/rate-limit", tags=["rate-limit"])


@router.get("/status", summary="Inspect client quota tier and Token Bucket status")
def get_rate_limit_status(request: Request):
    """
    Returns the caller's identified quota tier, current burst capacity,
    replenishment rate, and the global tier quota matrix.
    """
    client_key, tier = resolve_client_fingerprint(request)
    bucket = global_token_store.get_or_create(client_key, tier)

    tier_summary = {
        t.value: {
            "burst_capacity": int(q.capacity),
            "refill_rate_per_sec": q.refill_rate_per_sec,
            "sustained_per_minute": q.sustained_per_minute,
        }
        for t, q in TIER_QUOTAS.items()
    }

    return {
        "client_key": client_key,
        "tier": tier.value,
        "burst_capacity": int(bucket.capacity),
        "refill_rate_per_sec": bucket.refill_rate,
        "sustained_per_minute": bucket.refill_rate * 60.0,
        "tier_matrix": tier_summary,
    }
