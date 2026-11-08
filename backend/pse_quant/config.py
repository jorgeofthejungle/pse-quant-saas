"""
pse_quant/config.py — Central Configuration & Domain Constants
PSE Quant SaaS (v2 Rebuild)
"""

from __future__ import annotations
import os
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("PSE_DATA_DIR", BASE_DIR / "data"))
REPORTS_DIR = Path(os.getenv("PDF_OUTPUT_DIR", DATA_DIR / "reports"))

# ── Financial Valuation Constants ──────────────────────────────
PH_RISK_FREE_RATE: float = 0.065       # PH 10-year T-bond rate (~6.5%)
EQUITY_RISK_PREMIUM: float = 0.050     # Damodaran implied ERP for Philippines
DEFAULT_TARGET_PE: float = 15.0        # Baseline fair PE multiple for PSE
DDM_MAX_GROWTH_RATE: float = 0.07      # Cap on terminal DDM dividend growth rate
CONGLOMERATE_DISCOUNT: float = 0.20    # 20% holding-company discount for 'Holding Firms'

# Intrinsic Value Blend Weights: (DDM, EPS-PE, DCF)
IV_WEIGHTS: tuple[float, float, float] = (0.30, 0.35, 0.35)           # Unified
IV_WEIGHTS_DIVIDEND: tuple[float, float, float] = (0.50, 0.25, 0.25)  # Dividend focus
IV_WEIGHTS_VALUE: tuple[float, float, float] = (0.20, 0.40, 0.40)     # Value focus

# ── Margin of Safety Risk Premiums ─────────────────────────────
MOS_SIZE_PREMIUM: dict[str, float] = {
    "large": 0.0,    # > PHP 100B
    "mid": 1.5,      # PHP 20B - 100B
    "small": 3.0,    # PHP 5B - 20B
    "micro": 5.0,    # < PHP 5B
}

MOS_SECTOR_PREMIUM: dict[str, float] = {
    "Financials": 0.0,
    "Banking": 0.0,
    "Utilities": 0.0,
    "Property": 0.5,
    "Consumer": 0.5,
    "Industrial": 1.0,
    "Services": 1.0,
    "Holding Firms": 1.0,
    "Mining and Oil": 2.0,
    "Unknown": 1.5,
}
MOS_SECTOR_PREMIUM_DEFAULT: float = 1.0

# ── Scoring Weights & Thresholds ──────────────────────────────
MIN_SCORE_THRESHOLD: float = 45.0  # Dynamic threshold floor (mean + 0.5 SD applied above this)
MIN_SUBSCORES_PER_LAYER: int = 2   # Minimum non-null sub-scores to score a layer

# 3-Layer Fundamental Model Weights: Health / Improvement / Persistence
SCORER_WEIGHTS: dict[str, dict[str, float]] = {
    "unified":  {"health": 0.30, "improvement": 0.28, "persistence": 0.42},
    "dividend": {"health": 0.30, "improvement": 0.25, "persistence": 0.45},
    "value":    {"health": 0.35, "improvement": 0.30, "persistence": 0.35},
}

# Recency weighting for 3-year smoothed YoY deltas (newest first)
IMPROVEMENT_RECENCY_WEIGHTS: list[float] = [0.50, 0.30, 0.20]

# Confidence multiplier applied to final score based on complete data history
CONFIDENCE_TIERS: dict[int, float] = {
    5: 1.00,  # 5+ years
    4: 0.90,
    3: 0.80,
    2: 0.60,  # minimum viable
    1: 0.00,  # insufficient
}

# ── Sector Scoring Rules & Sub-score Weights ───────────────────
SECTOR_SCORING_CONFIG: dict[str, dict[str, dict[str, float]]] = {
    "bank": {
        "health": {
            "eps_stability": 0.35,
            "roe": 0.30,
            "pb": 0.20,
            "ni_margin": 0.15,
        },
        "improvement": {
            "eps_delta": 0.50,
            "revenue_delta": 0.50,
        },
        "persistence": {
            "eps": 0.40,
            "revenue": 0.30,
            "direction": 0.30,
        },
    },
    "reit": {
        "health": {
            "dividend_yield": 0.30,
            "eps_stability": 0.30,
            "de_ratio": 0.25,
            "roe": 0.15,
        },
        "improvement": {
            "revenue_delta": 0.45,
            "dps_delta": 0.30,
            "eps_delta": 0.25,
        },
        "persistence": {
            "dps": 0.35,
            "revenue": 0.35,
            "eps": 0.30,
        },
    },
    "holding": {
        "health": {
            "eps_stability": 0.35,
            "roe": 0.25,
            "pb": 0.25,
            "de_ratio": 0.15,
        },
        "improvement": {
            "eps_delta": 0.45,
            "revenue_delta": 0.35,
            "roe_delta": 0.20,
        },
        "persistence": {
            "direction": 0.35,
            "eps": 0.35,
            "revenue": 0.30,
        },
    },
    "property": {
        "health": {
            "de_ratio": 0.30,
            "eps_stability": 0.30,
            "ni_margin": 0.20,
            "roe": 0.20,
        },
        "improvement": {
            "revenue_delta": 0.50,
            "eps_delta": 0.50,
        },
        "persistence": {
            "revenue": 0.40,
            "eps": 0.30,
            "direction": 0.30,
        },
    },
    "industrial": {
        "health": {
            "eps_stability": 0.35,
            "roe": 0.30,
            "de_ratio": 0.20,
            "ni_margin": 0.15,
        },
        "improvement": {
            "eps_delta": 0.45,
            "revenue_delta": 0.35,
            "roe_delta": 0.20,
        },
        "persistence": {
            "direction": 0.35,
            "revenue": 0.35,
            "eps": 0.30,
        },
    },
    "mining": {
        "health": {
            "de_ratio": 0.40,
            "roe": 0.25,
            "eps_stability": 0.20,
            "ni_margin": 0.15,
        },
        "improvement": {
            "revenue_delta": 0.55,
            "eps_delta": 0.45,
        },
        "persistence": {
            "direction": 0.40,
            "revenue": 0.30,
            "eps": 0.30,
        },
    },
    "services": {
        "health": {
            "eps_stability": 0.35,
            "roe": 0.30,
            "de_ratio": 0.20,
            "ni_margin": 0.15,
        },
        "improvement": {
            "eps_delta": 0.45,
            "revenue_delta": 0.35,
            "roe_delta": 0.20,
        },
        "persistence": {
            "direction": 0.35,
            "revenue": 0.35,
            "eps": 0.30,
        },
    },
}
SECTOR_SCORING_CONFIG["general"] = SECTOR_SCORING_CONFIG["services"]

# ── Sector Whitelists & Overrides ──────────────────────────────
REIT_WHITELIST: set[str] = {"VREIT", "PREIT", "MREIT", "AREIT", "CREIT", "RCR", "FILRT", "DDMPR"}
BANK_TICKERS: set[str] = {"BDO", "MBT", "SECB", "BPI", "CHIB", "PNB", "UBP", "EW", "RCB", "AUB", "BNCOM", "CBC", "CSB", "PBB", "PBC", "PSB"}

SECTOR_MANUAL_MAP: dict[str, str] = {
    "BDO": "Financials", "MBT": "Financials", "SECB": "Financials", "MFIN": "Financials",
    "AC": "Holding Firms", "DMC": "Holding Firms", "FDC": "Holding Firms",
    "GTCAP": "Holding Firms", "LTG": "Holding Firms", "SM": "Holding Firms", "VLC": "Holding Firms",
    "LTL": "Holding Firms", "RCI": "Holding Firms", "ROX": "Holding Firms",
    "ALI": "Property", "CREIT": "Property", "FLI": "Property", "HOME": "Property",
    "HTI": "Property", "IDC": "Property", "KPPI": "Property", "LPC": "Property",
    "MREIT": "Property", "PREIT": "Property", "RCR": "Property", "SMPH": "Property",
    "VREIT": "Property", "AREIT": "Property", "DDMPR": "Property",
    "ALLDY": "Industrial", "BALAI": "Industrial", "CIC": "Industrial", "CNPF": "Industrial",
    "DELM": "Industrial", "DNL": "Industrial", "EMI": "Industrial", "FCG": "Industrial",
    "FRUIT": "Industrial", "GSMI": "Industrial", "JFC": "Industrial", "MEDIC": "Industrial",
    "MM": "Industrial", "MVC": "Industrial", "PGOLD": "Industrial", "PMPC": "Industrial",
    "RFM": "Industrial", "RRHI": "Industrial", "UPSON": "Industrial",
    "TECH": "Industrial", "PNC": "Industrial", "SBS": "Industrial", "SHLPH": "Industrial",
    "STN": "Industrial", "T": "Industrial", "URC": "Industrial", "VMC": "Industrial", "VITA": "Industrial",
    "BCOR": "Services", "BLOOM": "Services", "CEU": "Services", "ECP": "Services",
    "EEI": "Services", "FMETF": "Services", "GLO": "Services", "ICT": "Services",
    "IPO": "Services", "IS": "Services", "PAL": "Services", "PHC": "Services",
    "PLUS": "Services", "TEL": "Services", "TOP": "Services", "X": "Services", "XG": "Services",
    "ALTER": "Services", "ASLAG": "Services", "CREC": "Services", "MER": "Services",
    "MWC": "Services", "MYNLD": "Services", "REDC": "Services", "SPNEC": "Services", "VVT": "Services",
    "TUGS": "Services", "SEVN": "Services", "PIZZA": "Services", "SPC": "Services",
    "SSI": "Services", "STI": "Services", "TBGI": "Services", "WEB": "Services",
    "WPI": "Services", "WLCON": "Services",
    "SCC": "Mining and Oil",
}

# ── App & Infrastructure Settings ──────────────────────────────
DATABASE_URL: str | None = os.getenv("DATABASE_URL")
DATABASE_REPLICA_URL: str | None = os.getenv("DATABASE_REPLICA_URL")
DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "15"))
DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
DB_POOL_TIMEOUT: float = float(os.getenv("DB_POOL_TIMEOUT", "10.0"))
DB_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", "1800"))

DB_REPLICA_POOL_SIZE: int = int(os.getenv("DB_REPLICA_POOL_SIZE", "25"))
DB_REPLICA_MAX_OVERFLOW: int = int(os.getenv("DB_REPLICA_MAX_OVERFLOW", "20"))

RESEND_API_KEY: str | None = os.getenv("RESEND_API_KEY")
EMAIL_FROM: str = os.getenv("EMAIL_FROM", "StockPilot PH <reports@stockpilot.ph>")
ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")
PIPELINE_AI_MODEL: str = "claude-haiku-4-5-20251001"
