"""
pse_quant/scraper/etl.py — End-to-End PSE Edge Scraper & Scoring ETL Pipeline
Orchestrates:
  1. Directory sync (upsert stocks)
  2. Quote & dividend history sync (upsert prices & dps)
  3. Financial statement sync (upsert historical balance sheet & income statement)
  4. Scoring & Valuation computation (3-layer model + dynamic cutoff + MoS intrinsic value)
  5. Audit log tracking (PipelineRun)
"""

from __future__ import annotations
import logging
from datetime import datetime, date, timezone
from typing import Any
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from pse_quant.scraper.client import PseEdgeClient
from pse_quant.scraper.directory import fetch_all_companies, lookup_company
from pse_quant.scraper.stock_data import fetch_stock_quote, fetch_dividend_history
from pse_quant.scraper.financials import fetch_financial_reports
from pse_quant.db.models import Stock, Financial, Price, Score, PipelineRun
from pse_quant.core.metrics import (
    calculate_pe,
    calculate_pb,
    calculate_roe,
    calculate_de,
    calculate_dividend_yield,
    calculate_cagr,
    calculate_fcf,
    calculate_fcf_yield,
    calc_ffo,
    calc_ffo_yield,
)
from pse_quant.core.filters import filter_unified
from pse_quant.core.scoring import rank_stocks
from pse_quant.core.mos import enrich_stock_valuation
from pse_quant.core.validator import validate_financial_record

logger = logging.getLogger("pse_quant.scraper.etl")


def sync_directory(client: PseEdgeClient, session: Session) -> int:
    """
    Fetches the active company directory from PSE Edge and upserts Stock records.
    Returns count of processed stocks.
    """
    companies = fetch_all_companies(client)
    if not companies:
        logger.warning("No companies returned from directory scrape.")
        return 0

    count = 0
    for item in companies:
        ticker = item["ticker"].upper().strip()
        name = item.get("name", ticker)
        sector = item.get("sector", "General")
        cmpy_id = item.get("cmpy_id")

        is_reit = (
            ticker.endswith("REIT")
            or "REIT" in name.upper()
            or (sector == "Property" and "REIT" in ticker)
        )
        is_bank = sector == "Financials" and (
            "BANK" in name.upper()
            or ticker in ("BDO", "BPI", "MBT", "SECB", "CHIB", "PNB", "UBP", "EW", "RCB")
        )

        stock = session.get(Stock, ticker)
        if stock is None:
            stock = Stock(
                ticker=ticker,
                name=name,
                sector=sector,
                is_reit=is_reit,
                is_bank=is_bank,
                cmpy_id=cmpy_id,
                status="active",
            )
            session.add(stock)
        else:
            stock.name = name
            stock.sector = sector
            stock.is_reit = is_reit
            stock.is_bank = is_bank
            if cmpy_id:
                stock.cmpy_id = cmpy_id
        count += 1

    session.commit()
    logger.info(f"Directory sync completed: {count} stocks upserted.")
    return count


def sync_stock_quotes(
    client: PseEdgeClient,
    session: Session,
    tickers: list[str] | None = None,
) -> int:
    """
    Scrapes trading quotes (price, market cap) and cash dividends for designated stocks.
    """
    stmt = select(Stock).where(Stock.status == "active")
    if tickers:
        stmt = stmt.where(Stock.ticker.in_([t.upper().strip() for t in tickers]))

    stocks = session.scalars(stmt).all()
    count = 0
    today = date.today()

    for stock in stocks:
        if not stock.cmpy_id:
            resolved = lookup_company(client, stock.ticker)
            if resolved and resolved.get("cmpy_id"):
                stock.cmpy_id = resolved["cmpy_id"]
            else:
                continue

        quote = fetch_stock_quote(client, stock.cmpy_id)
        if quote and quote.get("close"):
            price_row = session.scalar(
                select(Price).where(
                    Price.ticker == stock.ticker,
                    Price.trade_date == today,
                )
            )
            if price_row is None:
                price_row = Price(
                    ticker=stock.ticker,
                    trade_date=today,
                    close=float(quote["close"]),
                    market_cap=float(quote["market_cap"]) if quote.get("market_cap") else None,
                )
                session.add(price_row)
            else:
                price_row.close = float(quote["close"])
                if quote.get("market_cap"):
                    price_row.market_cap = float(quote["market_cap"])

            stock.last_scraped_at = datetime.now(timezone.utc)
            count += 1

        # Also pull dividend declarations
        divs = fetch_dividend_history(client, stock.cmpy_id, stock.fiscal_year_end_month)
        for div_entry in divs:
            d_year = div_entry["year"]
            d_dps = div_entry["dps"]
            fin = session.scalar(
                select(Financial).where(
                    Financial.ticker == stock.ticker,
                    Financial.year == d_year,
                )
            )
            if fin:
                fin.dps = d_dps

    session.commit()
    logger.info(f"Quote sync completed: {count} stock prices updated.")
    return count


def sync_financials(
    client: PseEdgeClient,
    session: Session,
    tickers: list[str] | None = None,
) -> int:
    """
    Scrapes historical annual reports for designated stocks and updates Financial table.
    """
    stmt = select(Stock).where(Stock.status == "active")
    if tickers:
        stmt = stmt.where(Stock.ticker.in_([t.upper().strip() for t in tickers]))

    stocks = session.scalars(stmt).all()
    records_synced = 0

    for stock in stocks:
        if not stock.cmpy_id:
            continue

        fin_reports = fetch_financial_reports(client, stock.cmpy_id)
        for rep in fin_reports:
            validated = validate_financial_record(rep)
            year = validated.get("year")
            if not year:
                continue

            fin = session.scalar(
                select(Financial).where(
                    Financial.ticker == stock.ticker,
                    Financial.year == year,
                )
            )
            if fin is None:
                fin = Financial(
                    ticker=stock.ticker,
                    year=year,
                    revenue=validated.get("revenue"),
                    net_income=validated.get("net_income"),
                    equity=validated.get("equity"),
                    total_debt=validated.get("total_debt"),
                    eps=validated.get("eps"),
                    depreciation=validated.get("depreciation"),
                    amortization=validated.get("amortization"),
                    operating_cf=validated.get("operating_cash_flow"),
                    capex=validated.get("capital_expenditures"),
                )
                session.add(fin)
            else:
                if validated.get("revenue") is not None:
                    fin.revenue = validated["revenue"]
                if validated.get("net_income") is not None:
                    fin.net_income = validated["net_income"]
                if validated.get("equity") is not None:
                    fin.equity = validated["equity"]
                if validated.get("total_debt") is not None:
                    fin.total_debt = validated["total_debt"]
                if validated.get("eps") is not None:
                    fin.eps = validated["eps"]
                if validated.get("depreciation") is not None:
                    fin.depreciation = validated["depreciation"]
                if validated.get("amortization") is not None:
                    fin.amortization = validated["amortization"]
                if validated.get("operating_cash_flow") is not None:
                    fin.operating_cf = validated["operating_cash_flow"]
                if validated.get("capital_expenditures") is not None:
                    fin.capex = validated["capital_expenditures"]

            records_synced += 1

    session.commit()
    logger.info(f"Financials sync completed: {records_synced} annual statements upserted.")
    return records_synced


def build_stock_quant_dict(
    stock: Stock,
    latest_price: Price | None,
    financials: list[Financial],
) -> dict[str, Any]:
    """
    Converts ORM entities into the structured data dictionary expected by the
    quant scoring engine, filters, and intrinsic valuation models.
    """
    sorted_fins = sorted(financials, key=lambda f: f.year, reverse=True)
    f0 = sorted_fins[0] if sorted_fins else None

    price = latest_price.close if latest_price else None
    market_cap = latest_price.market_cap if latest_price else None

    rev_5y = [f.revenue for f in sorted_fins if f.revenue is not None][:5]
    ni_5y = [f.net_income for f in sorted_fins if f.net_income is not None][:5]
    eps_5y = [f.eps for f in sorted_fins if f.eps is not None][:5]
    dps_5y = [f.dps for f in sorted_fins if f.dps is not None][:5]
    ocf_5y = [f.operating_cf for f in sorted_fins if f.operating_cf is not None][:5]

    latest_rev = f0.revenue if f0 else None
    latest_ni = f0.net_income if f0 else None
    latest_eq = f0.equity if f0 else None
    latest_debt = f0.total_debt if f0 else None
    latest_eps = f0.eps if f0 else None
    latest_dps = dps_5y[0] if dps_5y else (f0.dps if f0 else None)

    roe = calculate_roe(latest_ni, latest_eq)
    de = calculate_de(latest_debt, latest_eq)
    pe = calculate_pe(price, latest_eps)
    div_yield = calculate_dividend_yield(latest_dps, price)

    # Price to book: estimate from market cap and equity, or raw bvps if available
    pb = None
    if market_cap and latest_eq and latest_eq > 0:
        pb = round(market_cap / (latest_eq * 1e6), 2)

    # Net Margin
    net_margin = None
    if latest_ni is not None and latest_rev and latest_rev > 0:
        net_margin = round((latest_ni / latest_rev) * 100.0, 2)

    # FCF and FCF Yield
    fcf = None
    fcf_yield = None
    fcf_per_share = None
    if f0 and f0.operating_cf is not None and f0.capex is not None:
        fcf = calculate_fcf(f0.operating_cf, f0.capex)
        if market_cap:
            fcf_yield = calculate_fcf_yield(fcf, market_cap / 1e6)
        if latest_eps and latest_ni and latest_ni > 0:
            implied_shares = (latest_ni * 1e6) / latest_eps
            if implied_shares > 0:
                fcf_per_share = round((fcf * 1e6) / implied_shares, 2)

    # CAGRs (5y or available)
    div_cagr = None
    if len(dps_5y) >= 2 and dps_5y[-1] and dps_5y[0] and dps_5y[-1] > 0:
        div_cagr = calculate_cagr(dps_5y[-1], dps_5y[0], len(dps_5y) - 1)

    rev_cagr = None
    if len(rev_5y) >= 2 and rev_5y[-1] and rev_5y[0] and rev_5y[-1] > 0:
        rev_cagr = calculate_cagr(rev_5y[-1], rev_5y[0], len(rev_5y) - 1)

    # REIT FFO metrics
    ffo = None
    ffo_yield = None
    if stock.is_reit and f0:
        ffo = calc_ffo(latest_ni, f0.depreciation)
        if market_cap and ffo:
            ffo_yield = calc_ffo_yield(ffo, market_cap / 1e6)

    return {
        "ticker": stock.ticker,
        "name": stock.name,
        "sector": stock.sector,
        "is_bank": stock.is_bank,
        "is_reit": stock.is_reit,
        "current_price": price,
        "market_cap": market_cap,
        "revenue": latest_rev,
        "net_income": latest_ni,
        "equity": latest_eq,
        "roe": roe,
        "net_margin": net_margin,
        "de_ratio": de,
        "pe": pe,
        "pb": pb,
        "eps": latest_eps,
        "dps_last": latest_dps,
        "dividend_yield": div_yield,
        "dividend_cagr_5y": div_cagr,
        "revenue_cagr": rev_cagr,
        "fcf": fcf,
        "fcf_yield": fcf_yield,
        "fcf_per_share": fcf_per_share,
        "ffo": ffo,
        "ffo_yield": ffo_yield,
        "eps_3y": eps_5y[:3],
        "eps_5y": eps_5y,
        "revenue_5y": rev_5y,
        "dividends_5y": dps_5y,
        "operating_cf_history": ocf_5y,
    }


def compute_scores_and_rankings(
    session: Session,
    portfolio_types: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """
    Loads all active equities from DB, evaluates filters, computes 3-layer scores,
    enriches with Margin of Safety intrinsic valuations, and upserts into Score table.
    """
    if portfolio_types is None:
        portfolio_types = ["unified", "dividend", "value"]

    stocks = session.scalars(select(Stock).where(Stock.status == "active")).all()
    today = date.today()

    # Preload latest price and financials for each stock
    stock_dicts: list[dict[str, Any]] = []
    fins_map: dict[str, list[dict[str, Any]]] = {}

    for stock in stocks:
        latest_price = session.scalar(
            select(Price)
            .where(Price.ticker == stock.ticker)
            .order_by(desc(Price.trade_date))
            .limit(1)
        )
        fins = session.scalars(
            select(Financial)
            .where(Financial.ticker == stock.ticker)
            .order_by(desc(Financial.year))
        ).all()

        s_dict = build_stock_quant_dict(stock, latest_price, list(fins))
        stock_dicts.append(s_dict)

        fins_map[stock.ticker] = [
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
            }
            for f in fins
        ]

    # Filter out companies failing baseline health gates
    eligible_stocks: list[dict[str, Any]] = []
    for s in stock_dicts:
        passed, _reason = filter_unified(s)
        if passed:
            eligible_stocks.append(s)

    results: dict[str, list[dict[str, Any]]] = {}

    for p_type in portfolio_types:
        ranked = rank_stocks(eligible_stocks, financials_map=fins_map, portfolio_type=p_type)

        enriched_ranked = []
        for s in ranked:
            enriched = enrich_stock_valuation(s, portfolio_type=p_type)
            enriched_ranked.append(enriched)

            # Upsert into Score table
            score_row = session.scalar(
                select(Score).where(
                    Score.ticker == enriched["ticker"],
                    Score.run_date == today,
                    Score.portfolio_type == p_type,
                )
            )
            if score_row is None:
                score_row = Score(
                    ticker=enriched["ticker"],
                    run_date=today,
                    portfolio_type=p_type,
                    score=enriched["score"],
                    rank=enriched.get("rank"),
                    confidence=enriched["confidence"],
                    category=enriched["category"],
                    breakdown_json=enriched,
                )
                session.add(score_row)
            else:
                score_row.score = enriched["score"]
                score_row.rank = enriched.get("rank")
                score_row.confidence = enriched["confidence"]
                score_row.category = enriched["category"]
                score_row.breakdown_json = enriched

        results[p_type] = enriched_ranked

    session.commit()
    logger.info(f"Quant scoring complete for portfolios: {portfolio_types}")
    return results


def run_pipeline(
    session: Session,
    client: PseEdgeClient | None = None,
    tickers: list[str] | None = None,
    sync_dir: bool = True,
    sync_quotes: bool = True,
    sync_fins: bool = True,
    portfolio_types: list[str] | None = None,
) -> PipelineRun:
    """
    Executes the comprehensive pipeline and records audit history to PipelineRun.
    """
    run_log = PipelineRun(run_type="daily_score", status="running")
    session.add(run_log)
    session.commit()

    summary: dict[str, Any] = {
        "sync_directory": 0,
        "sync_quotes": 0,
        "sync_financials": 0,
        "ranked_counts": {},
    }

    try:
        edge_client = client or PseEdgeClient()

        if sync_dir:
            summary["sync_directory"] = sync_directory(edge_client, session)

        if sync_quotes:
            summary["sync_quotes"] = sync_stock_quotes(edge_client, session, tickers=tickers)

        if sync_fins:
            summary["sync_financials"] = sync_financials(edge_client, session, tickers=tickers)

        ranked_results = compute_scores_and_rankings(session, portfolio_types=portfolio_types)
        for p_type, items in ranked_results.items():
            summary["ranked_counts"][p_type] = len(items)

        run_log.status = "completed"
        run_log.summary_json = summary
        run_log.completed_at = datetime.now(timezone.utc)
        session.commit()

    except Exception as e:
        logger.exception("Pipeline run encountered a critical error.")
        session.rollback()
        run_log.status = "failed"
        run_log.error_message = str(e)
        run_log.completed_at = datetime.now(timezone.utc)
        session.add(run_log)
        session.commit()
        raise

    return run_log
