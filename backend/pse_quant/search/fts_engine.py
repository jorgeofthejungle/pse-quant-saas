"""
pse_quant/search/fts_engine.py — SQLite FTS5 Full-Text Search Engine
PSE Quant SaaS (v2 Rebuild) — Lab 13

Provides sub-millisecond lexical search, Okapi BM25 relevance scoring,
prefix typeahead expansion, and keyword highlighting over Philippine Equities.
"""

from __future__ import annotations
import logging
import re
from typing import Dict, List, Optional, Any
from sqlalchemy import text, select
from sqlalchemy.orm import Session

from pse_quant.db.models import Stock

logger = logging.getLogger("pse_quant.search.fts")

# Curated alias dictionary for prominent Philippine equities (tickers -> nicknames, conglomerates, founders)
PSE_ALIASES: Dict[str, str] = {
    "ALI": "Ayala Land Real Estate Property Developer Commercial Residential Makati",
    "AC": "Ayala Corporation Parent Conglomerate Zobel De Ayala Holding",
    "ACEN": "ACEN Corporation Ayala Energy Renewables Solar Wind Power",
    "AREIT": "AREIT Ayala Land Commercial Real Estate Investment Trust REIT",
    "BDO": "Banco De Oro Universal Bank Henry Sy SM Group Banking Financials",
    "BPI": "Bank of the Philippine Islands Ayala Bank Financials Lending",
    "DMC": "DMCI Holdings DM Consunji Construction Mining Power Real Estate",
    "GLO": "Globe Telecom Ayala Singtel Mobile Broadband Cellular Telecommunications",
    "ICT": "International Container Terminal Services Enrique Razon Port Logistics Terminal Cargo",
    "JFC": "Jollibee Foods Corporation Tony Tan Caktiong Fast Food Chickenjoy Mang Inasal Chowking",
    "LTG": "LT Group Lucio Tan Tobacco Brewery Banking Fortune Tobacco Tanduay Asia Brewery",
    "MBT": "Metrobank Metropolitan Bank and Trust George Ty Banking Financials",
    "MER": "Manila Electric Company Meralco Power Distribution MVP Manny Pangilinan First Pacific",
    "MONDE": "Monde Nissin Lucky Me Quorn Betty Ang Noodles Food Consumer",
    "MPI": "Metro Pacific Investments MPIC Infrastructure Tollways Water Hospitals MVP",
    "NIKL": "Nickel Asia Mining Manuel Zamora Sumitomo Nickel Mining Metals",
    "PGOLD": "Puregold Price Club Lucio Co Retail Supermarket Grocery",
    "SCC": "Semirara Mining and Power Consunji Coal Energy Thermal",
    "SM": "SM Investments Corporation SMIC Henry Sy Conglomerate Mall Retail Banking",
    "SMPH": "SM Prime Holdings Henry Sy Mall Developer Property Commercial",
    "TEL": "PLDT Inc Philippine Long Distance Telephone Smart Telecom MVP Communications",
    "URC": "Universal Robina Corporation Gokongwei Jack n Jill C2 Piattos Snacks Beverage Food",
    "WLCON": "Wilcon Depot Belo Home Improvement Construction Retail Hardware",
}


def init_fts_tables(session: Session) -> None:
    """
    Creates the FTS5 virtual table if it doesn't already exist and ensures
    it is populated if the stocks table already contains records.
    """
    try:
        session.execute(text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS stocks_fts USING fts5(
                ticker,
                name,
                sector,
                aliases,
                tokenize='unicode61 remove_diacritics 2'
            );
        """))
        session.commit()

        # Check document count
        doc_count = session.execute(text("SELECT count(*) FROM stocks_fts;")).scalar() or 0
        if doc_count == 0:
            stock_count = session.execute(text("SELECT count(*) FROM stocks;")).scalar() or 0
            if stock_count > 0:
                logger.info("Initializing stocks_fts index from %d existing stocks...", stock_count)
                rebuild_fts_index(session)

    except Exception as exc:
        logger.warning("FTS5 table initialization skipped or failed: %s", exc)
        session.rollback()


def rebuild_fts_index(session: Session) -> int:
    """
    Drops existing FTS5 entries and re-indexes all active stocks from the primary stocks table.
    Returns the total number of indexed records.
    """
    session.execute(text("DELETE FROM stocks_fts;"))
    stocks = session.scalars(
        select(Stock).where(Stock.status.in_(["active", "Unknown"]) | Stock.status.is_(None))
    ).all()

    indexed = 0
    for s in stocks:
        aliases = PSE_ALIASES.get(s.ticker.upper(), s.name)
        session.execute(
            text("""
                INSERT INTO stocks_fts(ticker, name, sector, aliases)
                VALUES (:ticker, :name, :sector, :aliases);
            """),
            {
                "ticker": s.ticker.upper(),
                "name": s.name,
                "sector": s.sector or "Unknown",
                "aliases": aliases,
            }
        )
        indexed += 1

    session.commit()
    logger.info("Rebuilt stocks_fts index with %d equities.", indexed)
    return indexed


def sync_stock(
    session: Session,
    ticker: str,
    name: str,
    sector: str,
    aliases: Optional[str] = None,
) -> None:
    """Synchronizes an individual stock into the FTS5 inverted index."""
    norm_ticker = ticker.strip().upper()
    resolved_aliases = aliases or PSE_ALIASES.get(norm_ticker, name)

    # Delete existing entry if present
    session.execute(
        text("DELETE FROM stocks_fts WHERE ticker = :ticker;"),
        {"ticker": norm_ticker}
    )
    # Insert updated row
    session.execute(
        text("""
            INSERT INTO stocks_fts(ticker, name, sector, aliases)
            VALUES (:ticker, :name, :sector, :aliases);
        """),
        {
            "ticker": norm_ticker,
            "name": name.strip(),
            "sector": sector.strip(),
            "aliases": resolved_aliases.strip(),
        }
    )
    session.commit()


def delete_stock_from_index(session: Session, ticker: str) -> None:
    """Removes a delisted or deleted stock from the FTS5 index."""
    session.execute(
        text("DELETE FROM stocks_fts WHERE ticker = :ticker;"),
        {"ticker": ticker.strip().upper()}
    )
    session.commit()


def sanitize_query(raw_query: str) -> str:
    """
    Cleans raw user input and constructs a safe, tokenized FTS5 prefix expression.
    - Strips special FTS control characters and operators.
    - Wraps tokens in double quotes to prevent operator misinterpretation (e.g. '"AND"*').
    - Appends trailing wildcard '*' to each token for instant typeahead matching.
    """
    if not raw_query:
        return ""

    # Keep only unicode word characters and spaces
    cleaned = re.sub(r"[^\w\s]", " ", raw_query, flags=re.UNICODE).strip()
    tokens = cleaned.split()
    if not tokens:
        return ""

    # Wrap each valid token in double quotes with trailing wildcard
    fts_tokens = [f'"{t}"*' for t in tokens if len(t) >= 1]
    return " ".join(fts_tokens)


def search_stocks_fts(
    session: Session,
    raw_query: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Executes Okapi BM25 ranked lexical full-text search against stocks_fts.
    Uses column weighting:
      - Ticker: 15.0 (exact ticker hits score highest)
      - Company Name: 8.0
      - Aliases: 5.0
      - Sector: 2.0
    Pins exact uppercase ticker match to rank #1.
    """
    clean_query = sanitize_query(raw_query)
    if not clean_query:
        return []

    exact_ticker = raw_query.strip().upper()
    bounded_limit = max(1, min(limit, 50))

    query_sql = text("""
        SELECT 
            ticker,
            name,
            sector,
            aliases,
            highlight(stocks_fts, 0, '<mark>', '</mark>') AS highlighted_ticker,
            highlight(stocks_fts, 1, '<mark>', '</mark>') AS highlighted_name,
            bm25(stocks_fts, 15.0, 8.0, 2.0, 5.0) AS relevance_score
        FROM stocks_fts
        WHERE stocks_fts MATCH :query
        ORDER BY 
            CASE WHEN UPPER(ticker) = :exact_ticker THEN 0 ELSE 1 END,
            relevance_score ASC
        LIMIT :limit;
    """)

    try:
        rows = session.execute(
            query_sql,
            {
                "query": clean_query,
                "exact_ticker": exact_ticker,
                "limit": bounded_limit,
            }
        ).fetchall()
    except Exception as exc:
        logger.warning("FTS5 query failed for query '%s' ('%s'): %s", raw_query, clean_query, exc)
        return []

    results = []
    for r in rows:
        results.append({
            "ticker": r[0],
            "name": r[1],
            "sector": r[2],
            "aliases": r[3],
            "highlighted_ticker": r[4],
            "highlighted_name": r[5],
            "relevance_score": float(r[6]),
        })

    return results


def get_index_stats(session: Session) -> Dict[str, Any]:
    """Retrieves document counts and health metrics for the FTS5 index."""
    total_docs = session.execute(text("SELECT count(*) FROM stocks_fts;")).scalar() or 0
    total_stocks = session.execute(text("SELECT count(*) FROM stocks;")).scalar() or 0

    return {
        "fts_table": "stocks_fts",
        "total_indexed_documents": total_docs,
        "total_source_stocks": total_stocks,
        "is_synchronized": total_docs >= total_stocks and total_stocks > 0,
        "engine": "sqlite_fts5",
        "ranking_algorithm": "Okapi BM25",
        "column_weights": {
            "ticker": 15.0,
            "name": 8.0,
            "aliases": 5.0,
            "sector": 2.0,
        },
    }
