"""
pse_quant/search — Full-Text Search (FTS5) & Fast Lexical Retrieval
PSE Quant SaaS (v2 Rebuild) — Lab 13
"""

from pse_quant.search.fts_engine import (
    PSE_ALIASES,
    init_fts_tables,
    rebuild_fts_index,
    sync_stock,
    delete_stock_from_index,
    sanitize_query,
    search_stocks_fts,
    get_index_stats,
)
from pse_quant.search.service import FtsSearchService, search_service

__all__ = [
    "PSE_ALIASES",
    "init_fts_tables",
    "rebuild_fts_index",
    "sync_stock",
    "delete_stock_from_index",
    "sanitize_query",
    "search_stocks_fts",
    "get_index_stats",
    "FtsSearchService",
    "search_service",
]
