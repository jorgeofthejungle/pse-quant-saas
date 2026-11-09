"""
pse_quant/search/service.py — High-Level Full-Text Search & Discovery Service
PSE Quant SaaS (v2 Rebuild) — Lab 13

Orchestrates lexical search execution, metadata enrichment (latest price, market cap,
industry tags), and provides administrative index maintenance.
"""

from __future__ import annotations
import logging
import time
from typing import Dict, List, Optional, Any
from sqlalchemy import select

from pse_quant.db.connection import get_read_session, get_write_session
from pse_quant.db.models import Stock, Price
from pse_quant.search.fts_engine import (
    search_stocks_fts,
    rebuild_fts_index,
    get_index_stats,
    sync_stock,
    delete_stock_from_index,
)

logger = logging.getLogger("pse_quant.search.service")


class FtsSearchService:
    """Service layer for full-text search, typeahead autocomplete, and index sync."""

    @classmethod
    def search(
        cls,
        query: str,
        limit: int = 10,
        enrich_pricing: bool = True,
    ) -> Dict[str, Any]:
        """
        Executes sub-5ms BM25 full-text search and optionally enriches results
        with real-time price quotes, market caps, and REIT/Bank flags.
        """
        start_time = time.perf_counter()
        clean_query = query.strip() if query else ""

        if not clean_query:
            return {
                "query": "",
                "total_matches": 0,
                "execution_ms": 0.0,
                "results": [],
            }

        with get_read_session() as session:
            raw_results = search_stocks_fts(session, raw_query=clean_query, limit=limit)
            if not raw_results:
                duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
                return {
                    "query": clean_query,
                    "total_matches": 0,
                    "execution_ms": duration_ms,
                    "results": [],
                }

            matched_tickers = [r["ticker"] for r in raw_results]

            # Enrich with stock classification (is_reit, is_bank) and latest price
            stocks_map = {}
            stocks = session.scalars(
                select(Stock).where(Stock.ticker.in_(matched_tickers))
            ).all()
            for s in stocks:
                stocks_map[s.ticker] = s

            pricing_map = {}
            if enrich_pricing and matched_tickers:
                # Retrieve latest prices for matched tickers
                prices = session.scalars(
                    select(Price)
                    .where(Price.ticker.in_(matched_tickers))
                    .order_by(Price.trade_date.desc())
                ).all()
                for p in prices:
                    if p.ticker not in pricing_map:
                        pricing_map[p.ticker] = p

            enriched_results = []
            for item in raw_results:
                t = item["ticker"]
                stk = stocks_map.get(t)
                prc = pricing_map.get(t)

                enriched_results.append({
                    "ticker": t,
                    "name": item["name"],
                    "highlighted_name": item["highlighted_name"],
                    "highlighted_ticker": item["highlighted_ticker"],
                    "sector": item["sector"],
                    "is_reit": stk.is_reit if stk else False,
                    "is_bank": stk.is_bank if stk else False,
                    "close_price": round(prc.close, 2) if prc else None,
                    "market_cap": round(prc.market_cap, 2) if prc and prc.market_cap else None,
                    "relevance_score": item["relevance_score"],
                })

        duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        return {
            "query": clean_query,
            "total_matches": len(enriched_results),
            "execution_ms": duration_ms,
            "results": enriched_results,
        }

    @classmethod
    def rebuild_index(cls) -> Dict[str, Any]:
        """Admin action: completely drops and rebuilds stocks_fts from the stocks table."""
        start_time = time.perf_counter()
        with get_write_session() as session:
            count = rebuild_fts_index(session)
        duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        return {
            "status": "success",
            "indexed_count": count,
            "duration_ms": duration_ms,
            "message": f"Successfully indexed {count} equities into stocks_fts.",
        }

    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """Returns live statistics of the search index."""
        with get_read_session() as session:
            return get_index_stats(session)


# Singleton instance
search_service = FtsSearchService()
