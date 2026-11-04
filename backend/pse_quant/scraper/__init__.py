"""
pse_quant/scraper — PSE Edge Web Scraper and ETL Pipeline
"""

from pse_quant.scraper.client import PseEdgeClient
from pse_quant.scraper.directory import lookup_company, fetch_directory_by_sector, fetch_all_companies
from pse_quant.scraper.stock_data import fetch_stock_quote, fetch_dividend_history
from pse_quant.scraper.financials import fetch_financial_reports, parse_financial_html, detect_financial_unit
from pse_quant.scraper.etl import (
    sync_directory,
    sync_stock_quotes,
    sync_financials,
    build_stock_quant_dict,
    compute_scores_and_rankings,
    run_pipeline,
)

__all__ = [
    "PseEdgeClient",
    "lookup_company",
    "fetch_directory_by_sector",
    "fetch_all_companies",
    "fetch_stock_quote",
    "fetch_dividend_history",
    "fetch_financial_reports",
    "parse_financial_html",
    "detect_financial_unit",
    "sync_directory",
    "sync_stock_quotes",
    "sync_financials",
    "build_stock_quant_dict",
    "compute_scores_and_rankings",
    "run_pipeline",
]
