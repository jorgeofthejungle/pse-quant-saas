"""
pse_quant/services/stock_service.py — Stock Data Service
Handles data collection (PSE Edge scraping), persistent storage, and quant processing
for Philippine equities.
"""

from __future__ import annotations
import logging
from datetime import date, datetime, timezone
from typing import Any
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from pse_quant.scraper.client import PseEdgeClient
from pse_quant.scraper.etl import (
    sync_directory,
    sync_stock_quotes,
    sync_financials,
    compute_scores_and_rankings,
    run_pipeline,
    build_stock_quant_dict,
)
from pse_quant.db.models import Stock, Financial, Price, Score, PipelineRun
from pse_quant.core.mos import enrich_stock_valuation
from pse_quant.core.validator import validate_financial_record
from pse_quant.cache import global_cache


logger = logging.getLogger("pse_quant.services.stock")


class StockService:
    """Service layer for collecting, storing, and processing stock market data."""

    @staticmethod
    def collect_and_sync_all(
        session: Session,
        client: PseEdgeClient | None = None,
        tickers: list[str] | None = None,
    ) -> PipelineRun:
        """Executes full stock data collection, financial statement sync, and quant scoring."""
        return run_pipeline(session, client=client, tickers=tickers)

    @staticmethod
    def collect_quotes_only(
        session: Session,
        client: PseEdgeClient | None = None,
        tickers: list[str] | None = None,
    ) -> int:
        """Runs daily quote synchronization (price, market cap, dividend updates)."""
        edge_client = client or PseEdgeClient()
        return sync_stock_quotes(edge_client, session, tickers=tickers)

    @staticmethod
    def recompute_scores(
        session: Session,
        portfolio_types: list[str] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Re-runs the 3-layer deterministic scorer and MoS models across all active equities."""
        return compute_scores_and_rankings(session, portfolio_types=portfolio_types)

    @staticmethod
    def get_rankings(
        session: Session,
        portfolio_type: str = "unified",
        sector: str | None = None,
        min_score: float | None = None,
        min_mos: float | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Queries stored quantitative rankings with Cache-Aside lazy loading."""
        cache_key = f"stock:rankings:{portfolio_type}:{sector}:{min_score}:{min_mos}:{limit}"

        def _fetch():
            stmt = (
                select(Score)
                .where(Score.portfolio_type == portfolio_type)
                .order_by(Score.rank.asc())
            )
            if min_score is not None:
                stmt = stmt.where(Score.score >= min_score)

            scores = session.scalars(stmt).all()
            results: list[dict[str, Any]] = []

            for s in scores:
                if not s.breakdown_json:
                    continue
                data = dict(s.breakdown_json)
                data["rank"] = s.rank
                data["score"] = s.score
                data["category"] = s.category

                if sector and data.get("sector", "").lower() != sector.lower():
                    continue

                if min_mos is not None:
                    mos = data.get("mos_pct")
                    if mos is None or mos < min_mos:
                        continue

                results.append(data)
                if limit and len(results) >= limit:
                    break

            return results

        return global_cache.get_or_compute(
            key=cache_key,
            fetcher_fn=_fetch,
            ttl_seconds=300.0,
            tags=["stock", "rankings", f"portfolio:{portfolio_type}"],
        )

    @staticmethod
    def get_stock_profile(session: Session, ticker: str) -> dict[str, Any] | None:
        """
        Retrieves deep-dive equity profile with Cache-Aside lazy loading:
        core info, latest price, 5-year financials, full 3-layer scores + valuation models.
        """
        clean_ticker = ticker.upper().strip()
        cache_key = f"stock:profile:{clean_ticker}"

        def _fetch_profile():
            stock = session.get(Stock, clean_ticker)
            if not stock:
                return None

            latest_price = session.scalar(
                select(Price)
                .where(Price.ticker == clean_ticker)
                .order_by(desc(Price.trade_date))
                .limit(1)
            )

            financials = session.scalars(
                select(Financial)
                .where(Financial.ticker == clean_ticker)
                .order_by(desc(Financial.year))
                .limit(10)
            ).all()

            score_row = session.scalar(
                select(Score)
                .where(Score.ticker == clean_ticker, Score.portfolio_type == "unified")
                .order_by(desc(Score.run_date))
                .limit(1)
            )

            quant_dict = build_stock_quant_dict(stock, latest_price, list(financials))
            enriched_val = enrich_stock_valuation(quant_dict, portfolio_type="unified")
            breakdown = score_row.breakdown_json if score_row and score_row.breakdown_json else {}

            return {
                "ticker": stock.ticker,
                "name": stock.name,
                "sector": stock.sector,
                "is_bank": stock.is_bank,
                "is_reit": stock.is_reit,
                "status": stock.status,
                "cmpy_id": stock.cmpy_id,
                "last_scraped_at": stock.last_scraped_at.isoformat() if stock.last_scraped_at else None,
                "current_price": latest_price.close if latest_price else None,
                "market_cap": latest_price.market_cap if latest_price else None,
                "trade_date": latest_price.trade_date.isoformat() if latest_price else None,
                "score": score_row.score if score_row else None,
                "rank": score_row.rank if score_row else None,
                "category": score_row.category if score_row else "Watchlist",
                "confidence": score_row.confidence if score_row else 1.0,
                "intrinsic_value": enriched_val.get("intrinsic_value"),
                "mos_pct": enriched_val.get("mos_pct"),
                "mos_target_price": enriched_val.get("mos_target_price"),
                "valuation": enriched_val.get("valuation", {}),
                "layers": breakdown.get("breakdown", {}).get("layers", {}),
                "historical_financials": [
                    {
                        "year": f.year,
                        "revenue": f.revenue,
                        "net_income": f.net_income,
                        "equity": f.equity,
                        "total_debt": f.total_debt,
                        "eps": f.eps,
                        "dps": f.dps,
                        "operating_cf": f.operating_cf,
                        "capex": f.capex,
                        "depreciation": f.depreciation,
                    }
                    for f in financials
                ],
            }

        return global_cache.get_or_compute(
            key=cache_key,
            fetcher_fn=_fetch_profile,
            ttl_seconds=300.0,
            tags=["stock", f"stock:{clean_ticker}", "profile"],
        )

    @staticmethod
    def get_bargain_stocks(session: Session, min_mos: float = 0.0) -> list[dict[str, Any]]:
        """Returns qualifying equities currently trading below Intrinsic Value."""
        scores = session.scalars(
            select(Score)
            .where(Score.portfolio_type == "unified")
            .order_by(Score.rank.asc())
        ).all()

        bargains = []
        for s in scores:
            if not s.breakdown_json:
                continue
            mos = s.breakdown_json.get("mos_pct")
            if mos is not None and mos >= min_mos:
                bargains.append(s.breakdown_json)

        return bargains

    @staticmethod
    def override_financial_data(
        session: Session,
        ticker: str,
        year: int,
        data: dict[str, Any],
    ) -> Financial:
        """Admin control: Manually inserts or updates a financial record with validated data."""
        clean_ticker = ticker.upper().strip()
        stock = session.get(Stock, clean_ticker)
        if not stock:
            raise ValueError(f"Stock {clean_ticker} does not exist.")

        data["year"] = year
        validated = validate_financial_record(data)

        fin = session.scalar(
            select(Financial).where(
                Financial.ticker == clean_ticker,
                Financial.year == year,
            )
        )
        if fin is None:
            fin = Financial(ticker=clean_ticker, year=year)
            session.add(fin)

        for field in [
            "revenue", "net_income", "equity", "total_debt", "cash",
            "operating_cf", "capex", "ebitda", "eps", "dps", "depreciation", "amortization"
        ]:
            if field in validated and validated[field] is not None:
                setattr(fin, field, validated[field])

        session.commit()
        logger.info(f"Financial record for {clean_ticker} FY{year} manually updated by admin.")
        global_cache.invalidate(f"stock:profile:{clean_ticker}")
        global_cache.invalidate_pattern("stock:rankings:*")
        return fin
