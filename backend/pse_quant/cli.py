"""
pse_quant/cli.py — Command Line Interface for PSE Quant SaaS
Commands for running scraper ETL, scoring models, generating PDF reports,
sending email digests, and seeding demo data.
"""

from __future__ import annotations
import argparse
import sys
import os
import json
from datetime import date
from typing import Any
from sqlalchemy import select

from pse_quant.db.connection import get_session, init_db
from pse_quant.db.models import Stock, Financial, Price, Score, PipelineRun
from pse_quant.scraper.client import PseEdgeClient
from pse_quant.scraper.etl import run_pipeline, compute_scores_and_rankings
from pse_quant.reporting.generator import generate_pdf_report
from pse_quant.email.sender import send_weekly_report


def cmd_init_db(args: argparse.Namespace) -> None:
    print("[*] Initializing database tables...")
    init_db()
    print("[+] Database tables initialized.")


def cmd_seed_demo(args: argparse.Namespace) -> None:
    """Populates local database with rich benchmark equities for local development."""
    init_db()
    with get_session() as session:
        print("[*] Seeding benchmark PSE equities into database...")
        demo_stocks = [
            {
                "ticker": "DMC",
                "name": "DMCI Holdings, Inc.",
                "sector": "Holding Firms",
                "is_reit": False,
                "is_bank": False,
                "cmpy_id": "188",
                "price": 12.40,
                "market_cap": 164_670_000_000.0,
                "financials": [
                    {"year": 2024, "revenue": 123800.0, "net_income": 24800.0, "equity": 82500.0, "total_debt": 31200.0, "eps": 1.87, "dps": 1.44, "operating_cf": 28400.0, "capex": 8200.0},
                    {"year": 2023, "revenue": 115200.0, "net_income": 23100.0, "equity": 76400.0, "total_debt": 29500.0, "eps": 1.74, "dps": 1.30, "operating_cf": 26100.0, "capex": 7800.0},
                    {"year": 2022, "revenue": 104500.0, "net_income": 20900.0, "equity": 71200.0, "total_debt": 27100.0, "eps": 1.57, "dps": 1.20, "operating_cf": 24000.0, "capex": 7200.0},
                ],
            },
            {
                "ticker": "AREIT",
                "name": "AREIT, Inc.",
                "sector": "Property",
                "is_reit": True,
                "is_bank": False,
                "cmpy_id": "679",
                "price": 36.50,
                "market_cap": 64_300_000_000.0,
                "financials": [
                    {"year": 2024, "revenue": 8100.0, "net_income": 5300.0, "equity": 43200.0, "total_debt": 15400.0, "eps": 2.92, "dps": 2.58, "operating_cf": 5500.0, "capex": 600.0, "depreciation": 850.0},
                    {"year": 2023, "revenue": 7100.0, "net_income": 4600.0, "equity": 38900.0, "total_debt": 13800.0, "eps": 2.54, "dps": 2.24, "operating_cf": 4800.0, "capex": 500.0, "depreciation": 740.0},
                    {"year": 2022, "revenue": 6050.0, "net_income": 3950.0, "equity": 34800.0, "total_debt": 11900.0, "eps": 2.18, "dps": 1.95, "operating_cf": 4100.0, "capex": 420.0, "depreciation": 620.0},
                ],
            },
            {
                "ticker": "ICT",
                "name": "International Container Terminal Services, Inc.",
                "sector": "Services",
                "is_reit": False,
                "is_bank": False,
                "cmpy_id": "112",
                "price": 395.0,
                "market_cap": 810_000_000_000.0,
                "financials": [
                    {"year": 2024, "revenue": 142000.0, "net_income": 39500.0, "equity": 145000.0, "total_debt": 115000.0, "eps": 19.40, "dps": 9.20, "operating_cf": 52000.0, "capex": 22000.0},
                    {"year": 2023, "revenue": 127000.0, "net_income": 33200.0, "equity": 128000.0, "total_debt": 105000.0, "eps": 16.30, "dps": 7.80, "operating_cf": 44000.0, "capex": 19000.0},
                    {"year": 2022, "revenue": 112000.0, "net_income": 28100.0, "equity": 115000.0, "total_debt": 98000.0, "eps": 13.80, "dps": 6.50, "operating_cf": 38000.0, "capex": 16500.0},
                ],
            },
            {
                "ticker": "BDO",
                "name": "BDO Unibank, Inc.",
                "sector": "Financials",
                "is_reit": False,
                "is_bank": True,
                "cmpy_id": "89",
                "price": 148.0,
                "market_cap": 788_000_000_000.0,
                "financials": [
                    {"year": 2024, "revenue": 265000.0, "net_income": 78000.0, "equity": 540000.0, "total_debt": 3950000.0, "eps": 14.70, "dps": 4.40, "operating_cf": 85000.0, "capex": 8000.0},
                    {"year": 2023, "revenue": 234000.0, "net_income": 73400.0, "equity": 485000.0, "total_debt": 3650000.0, "eps": 13.80, "dps": 4.00, "operating_cf": 78000.0, "capex": 7500.0},
                    {"year": 2022, "revenue": 201000.0, "net_income": 57100.0, "equity": 440000.0, "total_debt": 3300000.0, "eps": 10.75, "dps": 3.20, "operating_cf": 62000.0, "capex": 6800.0},
                ],
            },
            {
                "ticker": "MER",
                "name": "Manila Electric Company",
                "sector": "Industrial",
                "is_reit": False,
                "is_bank": False,
                "cmpy_id": "145",
                "price": 412.0,
                "market_cap": 464_000_000_000.0,
                "financials": [
                    {"year": 2024, "revenue": 485000.0, "net_income": 41500.0, "equity": 138000.0, "total_debt": 142000.0, "eps": 36.80, "dps": 22.50, "operating_cf": 51000.0, "capex": 21000.0},
                    {"year": 2023, "revenue": 443000.0, "net_income": 38100.0, "equity": 125000.0, "total_debt": 135000.0, "eps": 33.80, "dps": 19.80, "operating_cf": 46000.0, "capex": 19500.0},
                    {"year": 2022, "revenue": 426000.0, "net_income": 28400.0, "equity": 112000.0, "total_debt": 128000.0, "eps": 25.20, "dps": 15.60, "operating_cf": 35000.0, "capex": 17800.0},
                ],
            },
        ]

        today = date.today()
        for d in demo_stocks:
            stock = session.get(Stock, d["ticker"])
            if not stock:
                stock = Stock(
                    ticker=d["ticker"],
                    name=d["name"],
                    sector=d["sector"],
                    is_reit=d["is_reit"],
                    is_bank=d["is_bank"],
                    cmpy_id=d["cmpy_id"],
                    status="active",
                )
                session.add(stock)

            price = session.scalar(
                select(Price).where(Price.ticker == d["ticker"], Price.trade_date == today)
            )
            if not price:
                price = Price(
                    ticker=d["ticker"],
                    trade_date=today,
                    close=d["price"],
                    market_cap=d["market_cap"],
                )
                session.add(price)

            for f_data in d["financials"]:
                fin = session.scalar(
                    select(Financial).where(Financial.ticker == d["ticker"], Financial.year == f_data["year"])
                )
                if not fin:
                    fin = Financial(ticker=d["ticker"], **f_data)
                    session.add(fin)

        session.commit()
        print(f"[+] Successfully seeded {len(demo_stocks)} benchmark equities.")

        # Compute initial scores
        print("[*] Computing scores and Margin of Safety valuations...")
        ranked = compute_scores_and_rankings(session, portfolio_types=["unified", "dividend", "value"])
        for p, items in ranked.items():
            print(f"    - {p.upper()}: {len(items)} qualifying stocks")
        print("[+] Seed and score complete.")


def cmd_score(args: argparse.Namespace) -> None:
    with get_session() as session:
        print("[*] Recomputing quantitative scores and rankings...")
        ranked = compute_scores_and_rankings(session)
        for p_type, items in ranked.items():
            print(f"\n=== Top {p_type.upper()} Stocks ===")
            for item in items[:5]:
                print(
                    f"#{item.get('rank', '-')} {item['ticker']} - Score: {item['score']:.1f} "
                    f"({item['category']}) | Price: PHP {item.get('current_price', 0):.2f} | "
                    f"IV: PHP {item.get('intrinsic_value', 0):.2f} | MoS: {item.get('mos_pct', 0)}%"
                )


def cmd_report(args: argparse.Namespace) -> None:
    with get_session() as session:
        out_path = args.output or "weekly_quant_report.pdf"
        # Load unified scores
        scores = session.scalars(
            select(Score)
            .where(Score.portfolio_type == "unified")
            .order_by(Score.rank.asc())
        ).all()
        stocks_data = [s.breakdown_json for s in scores if s.breakdown_json]
        if not stocks_data:
            print("[!] No scores found in database. Run 'python -m pse_quant.cli seed-demo' or 'score' first.")
            return

        print(f"[*] Generating PDF report to {out_path}...")
        path = generate_pdf_report(stocks_data, output_path=out_path)
        print(f"[+] Report generated successfully at: {path}")


def cmd_email_digest(args: argparse.Namespace) -> None:
    to_email = args.to
    if not to_email:
        print("[!] Must specify recipient with --to <email>")
        return

    with get_session() as session:
        scores = session.scalars(
            select(Score)
            .where(Score.portfolio_type == "unified")
            .order_by(Score.rank.asc())
        ).all()
        stocks_data = [s.breakdown_json for s in scores if s.breakdown_json]
        if not stocks_data:
            print("[!] No score data found. Please run seed-demo or scrape first.")
            return

        pdf_path = "weekly_report_temp.pdf"
        generate_pdf_report(stocks_data, output_path=pdf_path)

        print(f"[*] Sending weekly digest email to {to_email}...")
        res = send_weekly_report(to_email=to_email, top_stocks=stocks_data, pdf_attachment_path=pdf_path)
        print(f"[+] Send status: {res.get('status')} (id: {res.get('id')})")


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn
    print(f"[*] Starting StockPilot PH Quant Decision Server on http://{args.host}:{args.port}...")
    uvicorn.run("pse_quant.api.main:app", host=args.host, port=args.port, reload=args.reload)


def main() -> None:
    parser = argparse.ArgumentParser(description="PSE Quant SaaS Engine CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # serve
    p_serve = subparsers.add_parser("serve", help="Start FastAPI REST server")
    p_serve.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    p_serve.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    p_serve.add_argument("--reload", action="store_true", help="Enable auto-reload for development")

    # init-db
    subparsers.add_parser("init-db", help="Create database tables")

    # seed-demo
    subparsers.add_parser("seed-demo", help="Seed benchmark PSE equities into DB")

    # score
    subparsers.add_parser("score", help="Compute 3-layer scores and MoS intrinsic values")

    # report
    p_report = subparsers.add_parser("report", help="Generate executive PDF report")
    p_report.add_argument("--output", "-o", default="weekly_quant_report.pdf", help="Output PDF file path")

    # email-digest
    p_email = subparsers.add_parser("email-digest", help="Send email digest via Resend API")
    p_email.add_argument("--to", required=True, help="Recipient email address")

    # run-all
    p_run = subparsers.add_parser("run-all", help="Execute complete pipeline (sync, score, report)")
    p_run.add_argument("--tickers", nargs="*", help="Specific tickers to scrape")

    args = parser.parse_args()

    if args.command == "serve":
        cmd_serve(args)
    elif args.command == "init-db":
        cmd_init_db(args)
    elif args.command == "seed-demo":
        cmd_seed_demo(args)
    elif args.command == "score":
        cmd_score(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "email-digest":
        cmd_email_digest(args)
    elif args.command == "run-all":
        with get_session() as session:
            print("[*] Running full pipeline...")
            run_pipeline(session, tickers=args.tickers)
            print("[+] Pipeline complete.")


if __name__ == "__main__":
    main()
