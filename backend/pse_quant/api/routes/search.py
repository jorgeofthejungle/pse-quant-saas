"""
pse_quant/api/routes/search.py — Public Lexical Stock Search & Autocomplete API
PSE Quant SaaS (v2 Rebuild) — Lab 13

Provides instant, BM25-ranked full-text discovery for tickers, company names,
sectors, and common colloquial aliases.
"""

from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Query, Request

from pse_quant.search.service import search_service
from pse_quant.api.limiter import limiter

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", summary="Full-Text Search & Typeahead Autocomplete for PSE Equities")
@limiter.limit("60/minute")
def search_equities(
    request: Request,
    q: str = Query(..., min_length=1, max_length=100, description="Search query (e.g. 'MER', 'ayala', 'bank', 'meralco')"),
    limit: Optional[int] = Query(10, ge=1, le=50, description="Maximum matches to return"),
    enrich: Optional[bool] = Query(True, description="Whether to include latest price and market cap metrics"),
):
    """
    Executes sub-5ms BM25 full-text search against the SQLite FTS5 inverted index.
    Features:
      - Ticker exact match prioritization.
      - Trailing wildcard token expansion ('aya*' -> matches Ayala Land and Ayala Corp).
      - Highlighted search matches ('<mark>Ayala</mark> Land, Inc.').
      - Colloquial alias resolution (e.g. 'meralco' -> MER, 'banco de oro' -> BDO).
    """
    return search_service.search(query=q, limit=limit or 10, enrich_pricing=enrich if enrich is not None else True)
