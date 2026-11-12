"""
pse_quant/api/routes/edge.py — Edge Cache & Multi-Region Ingress Admin API
PSE Quant SaaS — Lab 18
"""

from __future__ import annotations
from fastapi import APIRouter, status
from pse_quant.edge.models import PurgeRequest, EdgeTelemetry
from pse_quant.edge.manager import edge_cache_manager

router = APIRouter(prefix="/admin/cache", tags=["admin-edge-cache"])


@router.get("/telemetry", response_model=EdgeTelemetry)
def get_edge_telemetry():
    """Retrieves live edge cache performance metrics, 304 hit ratios, and POP distribution."""
    return edge_cache_manager.get_telemetry()


@router.post("/purge", status_code=status.HTTP_200_OK)
def purge_edge_cache_tags(payload: PurgeRequest):
    """
    Broadcasts / registers an edge cache purge for specified surrogate tags.
    Invalidates cached content across global CDN POPs.
    """
    purged_count = edge_cache_manager.purge_tags(payload.tags)
    return {
        "status": "purged",
        "tags_purged": payload.tags,
        "count": purged_count,
        "actor": payload.actor,
    }


@router.post("/reset-metrics", status_code=status.HTTP_200_OK)
def reset_edge_telemetry():
    """Resets operational edge cache counters."""
    edge_cache_manager.reset()
    return {"status": "reset", "message": "Edge cache telemetry counters cleared"}
