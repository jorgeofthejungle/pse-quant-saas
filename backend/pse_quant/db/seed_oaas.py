"""
backend/pse_quant/db/seed_oaas.py — Seed Top-15 PSE Equities & OaaS Macro State
=============================================================================
Populates active macro baseline and empirical beta profiles for production readiness.
"""

from __future__ import annotations
import logging
from sqlalchemy import select
from pse_quant.db.connection import get_session, init_db
from pse_quant.db.models import Stock, Price, Financial, OaasMacroState
from pse_quant.core.oaas_engine import TickerBetaProfile

logger = logging.getLogger("pse_quant.db.seed_oaas")

# Empirical Sensitivity Profiles for the top 15 liquid PSE benchmark tickers + ILLIQ trap
PSE_BENCHMARK_PROFILES = {
    "BDO": {
        "name": "BDO Unibank, Inc.",
        "sector": "Banking",
        "is_bank": True,
        "is_reit": False,
        "price": 154.00,
        "mdtv_20": 280_000_000.0,
        "vol_daily": 0.014,
        "gross_dy": 0.026,
        "fcf_cov": 2.1,
        "is_holdco": False,
        "nav_disc": 0.0,
        "beta": TickerBetaProfile(beta_bsp=0.8, beta_us10y=0.4, beta_brent=-0.3, beta_usdphp=0.2, beta_msci=1.1),
    },
    "BPI": {
        "name": "Bank of the Philippine Islands",
        "sector": "Banking",
        "is_bank": True,
        "is_reit": False,
        "price": 126.50,
        "mdtv_20": 210_000_000.0,
        "vol_daily": 0.013,
        "gross_dy": 0.029,
        "fcf_cov": 2.3,
        "is_holdco": False,
        "nav_disc": 0.0,
        "beta": TickerBetaProfile(beta_bsp=0.75, beta_us10y=0.35, beta_brent=-0.25, beta_usdphp=0.15, beta_msci=1.05),
    },
    "MBT": {
        "name": "Metropolitan Bank & Trust Co.",
        "sector": "Banking",
        "is_bank": True,
        "is_reit": False,
        "price": 63.50,
        "mdtv_20": 130_000_000.0,
        "vol_daily": 0.012,
        "gross_dy": 0.047,
        "fcf_cov": 2.4,
        "is_holdco": False,
        "nav_disc": 0.0,
        "beta": TickerBetaProfile(beta_bsp=0.7, beta_us10y=0.3, beta_brent=-0.2, beta_usdphp=0.1, beta_msci=0.9),
    },
    "SM": {
        "name": "SM Investments Corporation",
        "sector": "Holding Firms",
        "is_bank": False,
        "is_reit": False,
        "price": 890.00,
        "mdtv_20": 220_000_000.0,
        "vol_daily": 0.013,
        "gross_dy": 0.018,
        "fcf_cov": 1.8,
        "is_holdco": True,
        "nav_disc": 0.28,
        "beta": TickerBetaProfile(beta_bsp=-0.3, beta_us10y=-0.4, beta_brent=-0.4, beta_usdphp=-0.5, beta_msci=1.3),
    },
    "AC": {
        "name": "Ayala Corporation",
        "sector": "Holding Firms",
        "is_bank": False,
        "is_reit": False,
        "price": 645.00,
        "mdtv_20": 175_000_000.0,
        "vol_daily": 0.014,
        "gross_dy": 0.016,
        "fcf_cov": 1.7,
        "is_holdco": True,
        "nav_disc": 0.32,
        "beta": TickerBetaProfile(beta_bsp=-0.35, beta_us10y=-0.45, beta_brent=-0.35, beta_usdphp=-0.55, beta_msci=1.25),
    },
    "AGI": {
        "name": "Alliance Global Group, Inc.",
        "sector": "Holding Firms",
        "is_bank": False,
        "is_reit": False,
        "price": 9.80,
        "mdtv_20": 65_000_000.0,
        "vol_daily": 0.016,
        "gross_dy": 0.021,
        "fcf_cov": 1.5,
        "is_holdco": True,
        "nav_disc": 0.44,
        "beta": TickerBetaProfile(beta_bsp=-0.3, beta_us10y=-0.4, beta_brent=-0.4, beta_usdphp=-0.4, beta_msci=0.95),
    },
    "DMC": {
        "name": "DMCI Holdings, Inc.",
        "sector": "Holding Firms",
        "is_bank": False,
        "is_reit": False,
        "price": 12.40,
        "mdtv_20": 85_000_000.0,
        "vol_daily": 0.015,
        "gross_dy": 0.116,
        "fcf_cov": 1.6,
        "is_holdco": True,
        "nav_disc": 0.18,
        "beta": TickerBetaProfile(beta_bsp=-0.2, beta_us10y=-0.3, beta_brent=0.5, beta_usdphp=0.4, beta_msci=0.8),
    },
    "SMPH": {
        "name": "SM Prime Holdings, Inc.",
        "sector": "Property",
        "is_bank": False,
        "is_reit": False,
        "price": 28.50,
        "mdtv_20": 190_000_000.0,
        "vol_daily": 0.014,
        "gross_dy": 0.018,
        "fcf_cov": 1.4,
        "is_holdco": False,
        "nav_disc": 0.0,
        "beta": TickerBetaProfile(beta_bsp=-0.7, beta_us10y=-0.6, beta_brent=-0.3, beta_usdphp=-0.4, beta_msci=1.15),
    },
    "ALI": {
        "name": "Ayala Land, Inc.",
        "sector": "Property",
        "is_bank": False,
        "is_reit": False,
        "price": 31.20,
        "mdtv_20": 180_000_000.0,
        "vol_daily": 0.015,
        "gross_dy": 0.022,
        "fcf_cov": 1.3,
        "is_holdco": False,
        "nav_disc": 0.0,
        "beta": TickerBetaProfile(beta_bsp=-0.75, beta_us10y=-0.65, beta_brent=-0.3, beta_usdphp=-0.45, beta_msci=1.2),
    },
    "AREIT": {
        "name": "AREIT, Inc.",
        "sector": "REITs",
        "is_bank": False,
        "is_reit": True,
        "price": 37.50,
        "mdtv_20": 45_000_000.0,
        "vol_daily": 0.012,
        "gross_dy": 0.072,
        "fcf_cov": 1.05,
        "is_holdco": False,
        "nav_disc": 0.0,
        "beta": TickerBetaProfile(beta_bsp=-1.2, beta_us10y=-0.9, beta_brent=0.0, beta_usdphp=-0.1, beta_msci=0.4),
    },
    "CREIT": {
        "name": "Citicore Energy REIT Corp.",
        "sector": "REITs",
        "is_bank": False,
        "is_reit": True,
        "price": 2.92,
        "mdtv_20": 28_000_000.0,
        "vol_daily": 0.011,
        "gross_dy": 0.082,
        "fcf_cov": 1.08,
        "is_holdco": False,
        "nav_disc": 0.0,
        "beta": TickerBetaProfile(beta_bsp=-1.1, beta_us10y=-0.85, beta_brent=0.1, beta_usdphp=0.0, beta_msci=0.35),
    },
    "MER": {
        "name": "Manila Electric Company",
        "sector": "Utilities",
        "is_bank": False,
        "is_reit": False,
        "price": 412.00,
        "mdtv_20": 110_000_000.0,
        "vol_daily": 0.011,
        "gross_dy": 0.052,
        "fcf_cov": 1.4,
        "is_holdco": False,
        "nav_disc": 0.0,
        "beta": TickerBetaProfile(beta_bsp=-0.2, beta_us10y=-0.2, beta_brent=-0.3, beta_usdphp=0.1, beta_msci=0.7),
    },
    "JFC": {
        "name": "Jollibee Foods Corporation",
        "sector": "Consumer",
        "is_bank": False,
        "is_reit": False,
        "price": 238.00,
        "mdtv_20": 185_000_000.0,
        "vol_daily": 0.016,
        "gross_dy": 0.012,
        "fcf_cov": 1.1,
        "is_holdco": False,
        "nav_disc": 0.0,
        "beta": TickerBetaProfile(beta_bsp=-0.4, beta_us10y=-0.5, beta_brent=-0.6, beta_usdphp=-0.8, beta_msci=1.2),
    },
    "URC": {
        "name": "Universal Robina Corporation",
        "sector": "Consumer",
        "is_bank": False,
        "is_reit": False,
        "price": 92.50,
        "mdtv_20": 95_000_000.0,
        "vol_daily": 0.015,
        "gross_dy": 0.038,
        "fcf_cov": 1.5,
        "is_holdco": False,
        "nav_disc": 0.0,
        "beta": TickerBetaProfile(beta_bsp=-0.35, beta_us10y=-0.4, beta_brent=-0.5, beta_usdphp=-0.7, beta_msci=1.0),
    },
    "TEL": {
        "name": "PLDT Inc.",
        "sector": "Services",
        "is_bank": False,
        "is_reit": False,
        "price": 1380.00,
        "mdtv_20": 120_000_000.0,
        "vol_daily": 0.012,
        "gross_dy": 0.068,
        "fcf_cov": 1.25,
        "is_holdco": False,
        "nav_disc": 0.0,
        "beta": TickerBetaProfile(beta_bsp=-0.2, beta_us10y=-0.3, beta_brent=-0.1, beta_usdphp=-0.3, beta_msci=0.85),
    },
    # Pre-Commitment Falsification Case
    "ILLIQ": {
        "name": "Speculative Penny Momentum Trap",
        "sector": "Mining and Oil",
        "is_bank": False,
        "is_reit": False,
        "price": 0.42,
        "mdtv_20": 350_000.0,
        "vol_daily": 0.048,
        "gross_dy": 0.0,
        "fcf_cov": 0.0,
        "is_holdco": False,
        "nav_disc": 0.0,
        "beta": TickerBetaProfile(beta_bsp=-0.2, beta_us10y=-0.1, beta_brent=-0.3, beta_usdphp=-0.2, beta_msci=0.0),
    },
}


def seed_oaas_baseline() -> None:
    """Initializes tables and seeds default macro state and benchmark equities."""
    init_db()
    with get_session() as session:
        # 1. Seed or Update Default Macro State
        active_state = session.scalar(
            select(OaasMacroState).where(OaasMacroState.is_active == True).order_by(OaasMacroState.id.desc())
        )
        if not active_state:
            active_state = OaasMacroState(
                regime_title="Neutral-to-Dovish Macro Drift & Selective Carry",
                z_bsp_rate=0.0,
                z_us10y_yield=0.4,
                z_brent_crude=-0.2,
                z_usd_php=0.5,
                z_msci_flow=0.3,
                php_10y_bval_rate=0.0585,
                is_active=True,
                source="hybrid_auto",
                metadata_json={
                    "bsp_policy_rate": 0.0575,
                    "usd_php_spot": 58.50,
                    "brent_spot_usd": 74.50,
                    "us10y_yield_pct": 4.40,
                },
            )
            session.add(active_state)
            print("[+] Seeded active OaaS Macro Baseline state.")

        # 2. Ensure all 16 benchmark tickers exist in the database
        for ticker, data in PSE_BENCHMARK_PROFILES.items():
            stock = session.get(Stock, ticker)
            if not stock:
                stock = Stock(
                    ticker=ticker,
                    name=data["name"],
                    sector=data["sector"],
                    is_bank=data["is_bank"],
                    is_reit=data["is_reit"],
                    status="active",
                )
                session.add(stock)
                session.flush()

            # Ensure price record exists
            latest_price = session.scalar(
                select(Price).where(Price.ticker == ticker).order_by(Price.trade_date.desc())
            )
            if not latest_price:
                price_rec = Price(
                    ticker=ticker,
                    trade_date=__import__("datetime").date.today(),
                    close=data["price"],
                    market_cap=data.get("mdtv_20", 1e9) * 100,  # approximate baseline
                )
                session.add(price_rec)

        session.commit()
        print(f"[+] Successfully verified and seeded {len(PSE_BENCHMARK_PROFILES)} benchmark tickers.")


if __name__ == "__main__":
    seed_oaas_baseline()
