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
from pse_quant.scraper.etl import run_pipeline, compute_scores_and_rankings, sync_directory
from pse_quant.reporting.generator import generate_pdf_report
from pse_quant.email.sender import send_weekly_report


def cmd_init_db(args: argparse.Namespace) -> None:
    print("[*] Initializing database tables...")
    init_db()
    print("[+] Database tables initialized.")


def cmd_sync_directory(args: argparse.Namespace) -> None:
    """Scrapes official PSE Edge directory and updates ticker database."""
    init_db()
    with get_session() as session:
        print("[*] Connecting to PSE Edge and updating ticker database...")
        client = PseEdgeClient()
        count = sync_directory(client, session)
        print(f"[+] Successfully updated ticker database: {count} listed equities synchronized into DB.")


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
            {
                "ticker": "AC",
                "name": "Ayala Corporation",
                "sector": "Holding Firms",
                "is_reit": False,
                "is_bank": False,
                "cmpy_id": "18",
                "price": 620.0,
                "market_cap": 384_000_000_000.0,
                "financials": [
                    {"year": 2024, "revenue": 342000.0, "net_income": 41200.0, "equity": 320000.0, "total_debt": 210000.0, "eps": 64.50, "dps": 11.20, "operating_cf": 58000.0, "capex": 24000.0},
                    {"year": 2023, "revenue": 315000.0, "net_income": 38100.0, "equity": 295000.0, "total_debt": 195000.0, "eps": 59.80, "dps": 10.40, "operating_cf": 52000.0, "capex": 22000.0},
                    {"year": 2022, "revenue": 280000.0, "net_income": 33500.0, "equity": 270000.0, "total_debt": 180000.0, "eps": 52.40, "dps": 9.60, "operating_cf": 46000.0, "capex": 19500.0},
                ],
            },
            {
                "ticker": "GLO",
                "name": "Globe Telecom, Inc.",
                "sector": "Services",
                "is_reit": False,
                "is_bank": False,
                "cmpy_id": "100",
                "price": 1980.0,
                "market_cap": 285_000_000_000.0,
                "financials": [
                    {"year": 2024, "revenue": 165000.0, "net_income": 24500.0, "equity": 95000.0, "total_debt": 172000.0, "eps": 168.00, "dps": 110.00, "operating_cf": 72000.0, "capex": 35000.0},
                    {"year": 2023, "revenue": 162000.0, "net_income": 24000.0, "equity": 88000.0, "total_debt": 168000.0, "eps": 165.00, "dps": 108.00, "operating_cf": 68000.0, "capex": 38000.0},
                    {"year": 2022, "revenue": 158000.0, "net_income": 34600.0, "equity": 82000.0, "total_debt": 160000.0, "eps": 240.00, "dps": 105.00, "operating_cf": 64000.0, "capex": 42000.0},
                ],
            },
            {
                "ticker": "SMPH",
                "name": "SM Prime Holdings, Inc.",
                "sector": "Property",
                "is_reit": False,
                "is_bank": False,
                "cmpy_id": "236",
                "price": 28.50,
                "market_cap": 825_000_000_000.0,
                "financials": [
                    {"year": 2024, "revenue": 142000.0, "net_income": 43800.0, "equity": 395000.0, "total_debt": 335000.0, "eps": 1.52, "dps": 0.46, "operating_cf": 54000.0, "capex": 42000.0},
                    {"year": 2023, "revenue": 128000.0, "net_income": 40000.0, "equity": 360000.0, "total_debt": 310000.0, "eps": 1.39, "dps": 0.40, "operating_cf": 48000.0, "capex": 38000.0},
                    {"year": 2022, "revenue": 105000.0, "net_income": 30100.0, "equity": 330000.0, "total_debt": 280000.0, "eps": 1.04, "dps": 0.35, "operating_cf": 41000.0, "capex": 35000.0},
                ],
            },
            {
                "ticker": "URC",
                "name": "Universal Robina Corporation",
                "sector": "Industrial",
                "is_reit": False,
                "is_bank": False,
                "cmpy_id": "252",
                "price": 94.00,
                "market_cap": 205_000_000_000.0,
                "financials": [
                    {"year": 2024, "revenue": 162000.0, "net_income": 13800.0, "equity": 118000.0, "total_debt": 65000.0, "eps": 6.35, "dps": 3.60, "operating_cf": 21000.0, "capex": 9000.0},
                    {"year": 2023, "revenue": 158000.0, "net_income": 12800.0, "equity": 112000.0, "total_debt": 60000.0, "eps": 5.90, "dps": 3.40, "operating_cf": 19500.0, "capex": 8500.0},
                    {"year": 2022, "revenue": 149000.0, "net_income": 14500.0, "equity": 108000.0, "total_debt": 58000.0, "eps": 6.65, "dps": 3.30, "operating_cf": 18000.0, "capex": 8200.0},
                ],
            },
            {
                "ticker": "ALI",
                "name": "Ayala Land, Inc.",
                "sector": "Property",
                "is_reit": False,
                "is_bank": False,
                "cmpy_id": "19",
                "price": 31.00,
                "market_cap": 462_000_000_000.0,
                "financials": [
                    {"year": 2024, "revenue": 168000.0, "net_income": 27800.0, "equity": 285000.0, "total_debt": 270000.0, "eps": 1.88, "dps": 0.65, "operating_cf": 38000.0, "capex": 32000.0},
                    {"year": 2023, "revenue": 148000.0, "net_income": 24500.0, "equity": 260000.0, "total_debt": 250000.0, "eps": 1.66, "dps": 0.58, "operating_cf": 34000.0, "capex": 29000.0},
                    {"year": 2022, "revenue": 126000.0, "net_income": 18600.0, "equity": 240000.0, "total_debt": 235000.0, "eps": 1.26, "dps": 0.48, "operating_cf": 28000.0, "capex": 26000.0},
                ],
            },
            {
                "ticker": "SCC",
                "name": "Semirara Mining and Power Corporation",
                "sector": "Mining and Oil",
                "is_reit": False,
                "is_bank": False,
                "cmpy_id": "226",
                "price": 32.50,
                "market_cap": 138_000_000_000.0,
                "financials": [
                    {"year": 2024, "revenue": 72000.0, "net_income": 21500.0, "equity": 74000.0, "total_debt": 22000.0, "eps": 5.05, "dps": 3.50, "operating_cf": 26000.0, "capex": 7500.0},
                    {"year": 2023, "revenue": 76000.0, "net_income": 27900.0, "equity": 70000.0, "total_debt": 24000.0, "eps": 6.55, "dps": 4.50, "operating_cf": 31000.0, "capex": 8000.0},
                    {"year": 2022, "revenue": 91000.0, "net_income": 39900.0, "equity": 62000.0, "total_debt": 26000.0, "eps": 9.38, "dps": 5.50, "operating_cf": 42000.0, "capex": 8500.0},
                ],
            },
            {
                "ticker": "WLCON",
                "name": "Wilcon Depot, Inc.",
                "sector": "Services",
                "is_reit": False,
                "is_bank": False,
                "cmpy_id": "664",
                "price": 18.20,
                "market_cap": 74_000_000_000.0,
                "financials": [
                    {"year": 2024, "revenue": 36500.0, "net_income": 3450.0, "equity": 24500.0, "total_debt": 6200.0, "eps": 0.84, "dps": 0.48, "operating_cf": 5800.0, "capex": 2400.0},
                    {"year": 2023, "revenue": 34600.0, "net_income": 3850.0, "equity": 22800.0, "total_debt": 5800.0, "eps": 0.94, "dps": 0.45, "operating_cf": 5500.0, "capex": 2200.0},
                    {"year": 2022, "revenue": 33500.0, "net_income": 3850.0, "equity": 20500.0, "total_debt": 5400.0, "eps": 0.94, "dps": 0.42, "operating_cf": 5200.0, "capex": 2100.0},
                ],
            },
            {
                "ticker": "CEB",
                "name": "Cebu Air, Inc.",
                "sector": "Services",
                "is_reit": False,
                "is_bank": False,
                "cmpy_id": "595",
                "price": 31.00,
                "market_cap": 34_000_000_000.0,
                "financials": [
                    {"year": 2024, "revenue": 92000.0, "net_income": 4100.0, "equity": 22000.0, "total_debt": 145000.0, "eps": 3.80, "dps": 0.00, "operating_cf": 24000.0, "capex": 22000.0},
                    {"year": 2023, "revenue": 90600.0, "net_income": 7900.0, "equity": 18000.0, "total_debt": 150000.0, "eps": 7.30, "dps": 0.00, "operating_cf": 22000.0, "capex": 19000.0},
                    {"year": 2022, "revenue": 56700.0, "net_income": -14000.0, "equity": 9800.0, "total_debt": 155000.0, "eps": -13.00, "dps": 0.00, "operating_cf": -3200.0, "capex": 14000.0},
                ],
            },
            {
                "ticker": "BLOOM",
                "name": "Bloomberry Resorts Corporation",
                "sector": "Services",
                "is_reit": False,
                "is_bank": False,
                "cmpy_id": "610",
                "price": 7.80,
                "market_cap": 88_000_000_000.0,
                "financials": [
                    {"year": 2024, "revenue": 48000.0, "net_income": 4200.0, "equity": 44000.0, "total_debt": 110000.0, "eps": 0.38, "dps": 0.00, "operating_cf": 12000.0, "capex": 14000.0},
                    {"year": 2023, "revenue": 48400.0, "net_income": 9500.0, "equity": 42000.0, "total_debt": 98000.0, "eps": 0.86, "dps": 0.00, "operating_cf": 18000.0, "capex": 16000.0},
                    {"year": 2022, "revenue": 38900.0, "net_income": 5100.0, "equity": 33000.0, "total_debt": 92000.0, "eps": 0.46, "dps": 0.00, "operating_cf": 14000.0, "capex": 12000.0},
                ],
            },
            {
                "ticker": "MEG",
                "name": "Megaworld Corporation",
                "sector": "Property",
                "is_reit": False,
                "is_bank": False,
                "cmpy_id": "144",
                "price": 2.10,
                "market_cap": 66_000_000_000.0,
                "financials": [
                    {"year": 2024, "revenue": 72000.0, "net_income": 18500.0, "equity": 240000.0, "total_debt": 120000.0, "eps": 0.58, "dps": 0.08, "operating_cf": 14000.0, "capex": 18000.0},
                    {"year": 2023, "revenue": 69700.0, "net_income": 17300.0, "equity": 222000.0, "total_debt": 115000.0, "eps": 0.54, "dps": 0.07, "operating_cf": 13000.0, "capex": 16500.0},
                    {"year": 2022, "revenue": 59500.0, "net_income": 15400.0, "equity": 205000.0, "total_debt": 110000.0, "eps": 0.48, "dps": 0.06, "operating_cf": 11500.0, "capex": 15000.0},
                ],
            },
            {
                "ticker": "FLI",
                "name": "Filinvest Land, Inc.",
                "sector": "Property",
                "is_reit": False,
                "is_bank": False,
                "cmpy_id": "92",
                "price": 0.65,
                "market_cap": 15_800_000_000.0,
                "financials": [
                    {"year": 2024, "revenue": 24000.0, "net_income": 3800.0, "equity": 98000.0, "total_debt": 84000.0, "eps": 0.16, "dps": 0.05, "operating_cf": 3500.0, "capex": 4500.0},
                    {"year": 2023, "revenue": 22500.0, "net_income": 3770.0, "equity": 95000.0, "total_debt": 82000.0, "eps": 0.16, "dps": 0.05, "operating_cf": 3200.0, "capex": 4200.0},
                    {"year": 2022, "revenue": 19900.0, "net_income": 2890.0, "equity": 92000.0, "total_debt": 79000.0, "eps": 0.12, "dps": 0.04, "operating_cf": 2800.0, "capex": 3800.0},
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
        res = send_weekly_report(to=to_email, pdf_path=pdf_path, top_stocks=stocks_data)
        print(f"[+] Send status: {res.get('status')} (id: {res.get('id')})")


def cmd_schedule_run(args: argparse.Namespace) -> None:
    from pse_quant.scheduler import execute_job
    print(f"[*] Running scheduled job: '{args.job}'...")
    res = execute_job(args.job)
    print(f"[+] Scheduled job finished with status: {res.get('status')}")
    if "summary" in res:
        print(f"    Summary: {res['summary']}")


def cmd_schedule_daemon(args: argparse.Namespace) -> None:
    from pse_quant.scheduler import run_scheduler_daemon
    print(f"[*] Starting StockPilot PH automated scheduler daemon (Poll Interval: {args.interval}s)...")
    run_scheduler_daemon(poll_interval=args.interval, max_iterations=args.max_iterations)


def cmd_oaas_seed(args: argparse.Namespace) -> None:
    from pse_quant.db.seed_oaas import seed_oaas_baseline
    print("[*] Seeding top-15 PSE equities and baseline macro state...")
    seed_oaas_baseline()
    print("[+] OaaS baseline seed completed.")


def cmd_oaas_triage(args: argparse.Namespace) -> None:
    from pse_quant.services.oaas_service import OaasService
    print(f"[*] Executing Daily Causal Shock Triage (dry_run={args.dry_run})...")
    res = OaasService.execute_daily_triage_and_dispatch(dry_run=args.dry_run)
    print(f"[+] Triage execution finished: {res}")


def cmd_oaas_weekly(args: argparse.Namespace) -> None:
    from pse_quant.services.oaas_service import OaasService
    print(f"[*] Compiling Sunday Weekly Regime Brief (dry_run={args.dry_run})...")
    res = OaasService.execute_weekly_brief_and_dispatch(dry_run=args.dry_run)
    print(f"[+] Weekly Brief finished: {res}")


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

    # sync-directory / update-tickers
    subparsers.add_parser("sync-directory", help="Scrape and synchronize full PSE company directory into database")
    subparsers.add_parser("update-tickers", help="Alias for sync-directory")

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

    # schedule-run
    p_sched_run = subparsers.add_parser("schedule-run", help="Execute an automated scheduled task on demand")
    p_sched_run.add_argument(
        "--job",
        choices=["quotes_sync", "morning_alerts", "weekly_report", "oaas_triage", "oaas_weekly"],
        default="quotes_sync",
        help="Scheduled task to trigger",
    )

    # oaas-seed
    subparsers.add_parser("oaas-seed", help="Seed top-15 PSE equities and baseline macro shock state")

    # oaas-triage
    p_oaas_triage = subparsers.add_parser("oaas-triage", help="Run daily post-market Causal Shock Triage & Instant Alert check")
    p_oaas_triage.add_argument("--dry-run", action="store_true", help="Simulate evaluation without dispatching real emails")

    # oaas-weekly
    p_oaas_weekly = subparsers.add_parser("oaas-weekly", help="Run Sunday Weekly Regime Brief compilation and broadcast")
    p_oaas_weekly.add_argument("--dry-run", action="store_true", help="Simulate compilation without dispatching real emails")

    # schedule-daemon
    p_sched_daemon = subparsers.add_parser("schedule-daemon", help="Run continuous background scheduler daemon")
    p_sched_daemon.add_argument("--interval", type=int, default=60, help="Polling interval in seconds")
    p_sched_daemon.add_argument("--max-iterations", type=int, default=None, help="Optional max iterations for testing")

    args = parser.parse_args()

    if args.command == "serve":
        cmd_serve(args)
    elif args.command == "init-db":
        cmd_init_db(args)
    elif args.command in ("sync-directory", "update-tickers"):
        cmd_sync_directory(args)
    elif args.command == "seed-demo":
        cmd_seed_demo(args)
    elif args.command == "score":
        cmd_score(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "email-digest":
        cmd_email_digest(args)
    elif args.command == "schedule-run":
        cmd_schedule_run(args)
    elif args.command == "schedule-daemon":
        cmd_schedule_daemon(args)
    elif args.command == "oaas-seed":
        cmd_oaas_seed(args)
    elif args.command == "oaas-triage":
        cmd_oaas_triage(args)
    elif args.command == "oaas-weekly":
        cmd_oaas_weekly(args)
    elif args.command == "run-all":
        with get_session() as session:
            print("[*] Running full pipeline...")
            run_pipeline(session, tickers=args.tickers)
            print("[+] Pipeline complete.")


if __name__ == "__main__":
    main()
