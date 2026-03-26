# ============================================================
# config.py — Central Configuration
# PSE Quant SaaS
# ============================================================
# Edit this file to set your Discord webhook URLs.
# All other settings can be left as defaults to start.
# ============================================================

# ── Discord Webhook URLs ───────────────────────────────────
# How to get a webhook URL:
# 1. Open your Discord server
# 2. Click the gear icon next to a channel → Integrations → Webhooks
# 3. Click "New Webhook" → Copy Webhook URL
# 4. Paste the URL below for the matching channel

DISCORD_WEBHOOKS = {
    'dividend': '',   # paste #pse-dividend webhook URL here
    'value':    '',   # paste #pse-value webhook URL here
    'alerts':   '',   # paste #pse-alerts webhook URL here (price/earnings alerts)
}

# ── Report Output Directory ────────────────────────────────
# Where generated PDF reports are saved locally.
# Defaults to a 'reports_output' folder inside the project.
import os
REPORTS_DIR = os.path.join(os.path.dirname(__file__), 'data', 'reports')

# ── Data Directories ───────────────────────────────────────
DATA_DIR   = os.path.join(os.path.dirname(__file__), 'data')
RAW_DIR    = os.path.join(DATA_DIR, 'raw')
PARSED_DIR = os.path.join(DATA_DIR, 'parsed')

# ── Scheduling ─────────────────────────────────────────────
# Weekly report: every Sunday at 8:00 AM Philippine time
WEEKLY_REPORT_DAY  = 'sun'
WEEKLY_REPORT_HOUR = 8
WEEKLY_REPORT_TZ   = 'Asia/Manila'

# Daily alert check: every weekday at 9:00 AM
DAILY_ALERT_HOUR   = 9
DAILY_ALERT_MINUTE = 0

# Daily report: send PDF at 6 PM if rankings changed since 4 PM score run
DAILY_REPORT_HOUR   = 18
DAILY_REPORT_MINUTE = 0

# ── PSE Edge Settings ──────────────────────────────────────
PSE_EDGE_BASE_URL   = 'https://edge.pse.com.ph'
SCRAPE_DELAY_SECS   = 3     # seconds between requests — be respectful
REQUEST_TIMEOUT     = 30    # seconds before a request times out
MAX_RETRIES         = 3     # number of retry attempts for failed requests

# ── AI Model Selection ─────────────────────────────────────
# Pipeline runs (sentiment analysis, news classification):
#   → Use Haiku — fast, cheap, sufficient for classification tasks.
# Self-repair / error analysis (if AI-assisted code correction is added):
#   → Use Sonnet — smarter, better at reasoning about code errors.
PIPELINE_AI_MODEL   = "claude-haiku-4-5-20251001"   # sentiment, news, classification
SELF_REPAIR_MODEL   = "claude-sonnet-4-6"            # error diagnosis, code repair

# ── Financial Model Settings ───────────────────────────────
# These match the values in mos.py — update both if you change them
PH_RISK_FREE_RATE   = 0.065   # PH 10-year T-bond rate (~6.5%)
EQUITY_RISK_PREMIUM = 0.050   # PSE equity risk premium (~5.0%)
DEFAULT_TARGET_PE   = 15.0    # Fair PE multiple for Philippine market
DDM_MAX_GROWTH_RATE = 0.07    # Cap on DDM dividend growth rate

# ── Data Lookback ──────────────────────────────────────────
YEARS_PREFERRED = 5   # Use 5 years of data when available
YEARS_MINIMUM   = 3   # Require at least 3 years; flag stocks with less

# ── Conglomerate IV Discount ───────────────────────────────
# Applied to intrinsic value for stocks in the 'Holding Firms' sector.
# Philippine conglomerates trade at a structural discount due to opacity,
# cross-holding complexity, and limited segment-level reporting.
CONGLOMERATE_DISCOUNT = 0.20   # 20% reduction to intrinsic value

# ── PDF Trigger Threshold ──────────────────────────────────
# Send a new PDF if any top-10 stock's score shifts by this many points
SCORE_CHANGE_THRESHOLD = 5.0

# ── Minimum Score Floor ──────────────────────────────────
# Stocks scoring below this threshold are excluded from the PDF report.
# 50 = only "Strong Growth" and above make the cut.
MIN_SCORE_THRESHOLD = 45  # Hard floor — dynamic threshold (mean+0.5SD) is applied on top of this

# ── Weekly Full Financial Scrape ───────────────────────────
WEEKLY_SCRAPE_DAY  = 'sun'
WEEKLY_SCRAPE_HOUR = 22    # 10:00 PM PHT — after-hours, before Monday market

# ── Stale Data Detection ───────────────────────────────────
# If a stock's latest price is older than WARN days, print a warning but
# still allow scoring.  If older than BLOCK days, the stock is hard-blocked
# from scoring (likely suspended or delisted).
STALE_PRICE_WARN_DAYS  = 30
STALE_PRICE_BLOCK_DAYS = 90

# Fine-grained price staleness thresholds (used by check_price_staleness()).
# WARN: flag the stock as stale in the staleness report (5 trading days = ~1 week).
# ERROR: critical — stock is likely suspended or data pipeline is broken.
# MARKET_CAP: market cap is considered stale after this many calendar days.
PRICE_STALENESS_WARN_DAYS    = 5    # warn if price older than 5 calendar days
PRICE_STALENESS_ERROR_DAYS   = 30   # critical block if price older than 30 days
MARKET_CAP_STALENESS_DAYS    = 30   # market_cap stale if price row older than 30 days

# How many days without a PSE Edge scrape before a ticker is auto-marked
# as 'suspended' during the weekly scrape comparison.
STALE_SCRAPE_SUSPEND_DAYS = 14

# ── Scheduler Heartbeat ─────────────────────────────────────
# If the daily scoring job hasn't run in this many hours, dashboard shows WARNING.
SCHEDULER_HEARTBEAT_WARN_HOURS = 26

# ── Admin Access ───────────────────────────────────────────
# Your Discord snowflake ID — only this user can use /admin commands.
# Set ADMIN_DISCORD_ID in .env (never hardcode here).
import os as _os
ADMIN_DISCORD_ID = _os.getenv('ADMIN_DISCORD_ID', '')

# ── Fundamental Momentum ───────────────────────────────────
# Minimum historical data points required to compute any momentum signal.
# With 4 points: 2 recent vs 2 prior (minimal but usable).
# Stocks with fewer data points receive None -- _blend() redistributes weight.
MOMENTUM_MIN_YEARS = 4

# ── Improvement Layer Recency Weighting ──────────────────
# Applied to 3-year smoothed deltas in scorer_improvement.py.
# Most recent YoY change gets 50% weight, then 30%, then 20%.
IMPROVEMENT_RECENCY_WEIGHTS = [0.50, 0.30, 0.20]  # newest first

# ── REIT Classification Whitelist ────────────────────────
# Tickers that must always be classified as REIT (is_reit=1).
# These were initially misclassified during scraping.
REIT_WHITELIST = {'VREIT', 'PREIT', 'MREIT', 'AREIT'}
#
# REIT FFO Exemption (scorer_health.py):
# REITs are legally required to distribute 90%+ of distributable income as
# dividends. This means their FCF (after mandatory distributions) is
# structurally near zero or negative — not because they are unhealthy, but
# by design. For REITs, scorer_health.py substitutes FFO yield (Funds From
# Operations = Net Income + Depreciation) in place of FCF yield.
# If depreciation data is unavailable, the FCF component scores as neutral
# (50/100) rather than zero, avoiding unfair penalisation.
# FFO data source: requires 'depreciation' field in financials table (Phase 12).

# ── Data Confidence Tiers ────────────────────────────────────
# Multiplier applied to final score based on years of complete data.
# Complete = EPS + Revenue + OCF all present for a given year.
CONFIDENCE_TIERS = {
    5: 1.00,  # 5+ years
    4: 0.90,
    3: 0.80,
    2: 0.65,
    1: 0.00,  # not scored
}

# ── Health Layer Thresholds (PSE percentile-based) ───────
# Fallback values used when calibration has not yet run.
# calibrate_thresholds.py overwrites these in the settings table.
HEALTH_THRESHOLDS = {
    'roe':              {'p90': 20.0, 'p75': 14.0, 'p50': 9.0,  'p25': 4.0},
    'ocf_margin':       {'p90': 22.0, 'p75': 15.0, 'p50': 9.0,  'p25': 3.0},
    'fcf_yield':        {'p90': 10.0, 'p75': 6.5,  'p50': 3.5,  'p25': 1.0},
    'eps_stability_cv': {'p90': 0.10, 'p75': 0.25, 'p50': 0.50, 'p25': 0.80},
}
# Note: For eps_stability_cv, lower is better (p90 = most stable 10%).

# ── MoS Risk-Adjusted Discount Rate ─────────────────────
# Size premiums added to base discount rate (percentage points)
MOS_SIZE_PREMIUM = {
    'large': 0.0,    # > PHP 100B market cap
    'mid':   1.5,    # PHP 20B-100B
    'small': 3.0,    # PHP 5B-20B
    'micro': 5.0,    # < PHP 5B
}

# Sector-specific risk premiums (percentage points)
MOS_SECTOR_PREMIUM = {
    'Financials':    0.0,
    'Banking':       0.0,
    'Utilities':     0.0,
    'Property':      0.5,
    'Consumer':      0.5,
    'Industrial':    1.0,
    'Services':      1.0,
    'Holding Firms': 1.0,
    'Mining and Oil': 2.0,
    'Unknown':       1.5,
}
MOS_SECTOR_PREMIUM_DEFAULT = 1.0  # fallback for unrecognised sectors

# ── Scorer Layer Weights ─────────────────────────────────
# 3-layer weights (Acceleration folded into Improvement momentum bonus).
SCORER_WEIGHTS = {
    'unified':  {'health': 0.30, 'improvement': 0.28, 'persistence': 0.42},
    'dividend': {'health': 0.30, 'improvement': 0.25, 'persistence': 0.45},
    'value':    {'health': 0.35, 'improvement': 0.30, 'persistence': 0.35},
}

# ── Dynamic Reweighting ───────────────────────────────────
# Minimum number of non-None sub-scores required for a layer to produce
# a valid score. If fewer are available, the layer returns None and its
# weight is redistributed to the other layers.
MIN_SUBSCORES_PER_LAYER = 2

# ── Sector Classification ─────────────────────────────────
# Tickers that are banks but PSE Edge did not label them correctly.
BANK_TICKERS = {'BDO', 'MBT', 'SECB'}

# ── Feedback Loop Thresholds ───────────────────────────────
# Configurable thresholds for the 3-tier feedback system.
# Validated empirically during first 3 months of operation.
# Do NOT hardcode these in logic files — always import from config.

SCORE_CHANGE_MINOR_THRESHOLD   = 15    # abs score shift to trigger 'minor' flag
SCORE_CHANGE_MAJOR_THRESHOLD   = 30    # abs score shift to trigger 'major' flag
BLIND_SPOT_SCORE_THRESHOLD     = 70    # min score for blind spot detection
BLIND_SPOT_RETURN_THRESHOLD    = 0.10  # negative return threshold (decimal)
SECTOR_BIAS_Z_THRESHOLD        = 1.0   # z-score for flagging sector bias
THIN_MONTH_THRESHOLD           = 15    # min matched stocks for valid month
MOS_HIT_THRESHOLD              = 0.15  # MoS cutoff for predicted upside (decimal)
SCORE_INSTABILITY_ALERT_MONTHS = 3     # consecutive flagged months before DM
SECTOR_MIN_BANKS               = 3     # min stocks for bank sector evaluation
SECTOR_MIN_REITS               = 4     # min stocks for REIT sector evaluation
SECTOR_MIN_DEFAULT             = 5     # min stocks for all other sectors


# Manual sector fixes for the 70 stocks scraped as "Unknown".
# Maps ticker → PSE sector string (must match values used in the stocks table).
SECTOR_MANUAL_MAP = {
    # Banks (Financials)
    'BDO':   'Financials', 'MBT':  'Financials', 'SECB': 'Financials',
    'MFIN':  'Financials',
    # Holding Firms
    'AC':    'Holding Firms', 'DMC':   'Holding Firms', 'FDC':   'Holding Firms',
    'GTCAP': 'Holding Firms', 'LTG':   'Holding Firms', 'SM':    'Holding Firms',
    'VLC':   'Holding Firms',
    # Property / Real Estate
    'ALI':   'Property', 'CREIT': 'Property', 'FLI':   'Property',
    'HOME':  'Property', 'HTI':   'Property', 'IDC':   'Property',
    'KPPI':  'Property', 'LPC':   'Property', 'MREIT': 'Property',
    'PREIT': 'Property', 'RCR':   'Property', 'SMPH':  'Property',
    'VREIT': 'Property', 'AREIT': 'Property',
    # Industrial / Consumer / Food
    'ALLDY': 'Industrial', 'BALAI': 'Industrial', 'CIC':   'Industrial',
    'CNPF':  'Industrial', 'DELM':  'Industrial', 'DNL':   'Industrial',
    'EMI':   'Industrial', 'FCG':   'Industrial', 'FRUIT': 'Industrial',
    'GSMI':  'Industrial', 'JFC':   'Industrial', 'MEDIC': 'Industrial',
    'MM':    'Industrial', 'MVC':   'Industrial', 'PGOLD': 'Industrial',
    'PMPC':  'Industrial', 'RFM':   'Industrial', 'RRHI':  'Industrial',
    'UPSON': 'Industrial',
    # Services / Telecom / Tech / Transport
    'BCOR':  'Services', 'BLOOM': 'Services', 'CEU':   'Services',
    'ECP':   'Services', 'EEI':   'Services', 'FMETF': 'Services',
    'GLO':   'Services', 'ICT':   'Services', 'IPO':   'Services',
    'IS':    'Services', 'PAL':   'Services', 'PHC':   'Services',
    'PLUS':  'Services', 'TEL':   'Services', 'TOP':   'Services',
    'X':     'Services', 'XG':    'Services',
    # Utilities / Energy
    'ALTER': 'Services', 'ASLAG': 'Services', 'CREC':  'Services',
    'MER':   'Services', 'MWC':   'Services', 'MYNLD': 'Services',
    'REDC':  'Services', 'SPNEC': 'Services', 'VVT':   'Services',
}

# ── Sector-Specific Scoring Config ───────────────────────
# Defines sub-score weights within each layer per scoring group.
# Keys must match sub-score function names in each scorer module.
# Weights within a layer must sum to 1.0.
# _blend() handles None sub-scores by redistributing weight dynamically.
SECTOR_SCORING_CONFIG = {
    'bank': {
        'health': {
            'eps_stability': 0.35,  # Best proxy for credit quality / risk
            'roe':           0.30,  # Core efficiency for banks
            'pb':            0.20,  # Banks trade on book value
            'ni_margin':     0.15,  # Proxy for NIM (capped — noisy)
            # D/E excluded: leverage IS the business model for banks
        },
        'improvement': {
            'eps_delta':     0.50,  # Primary earnings signal
            'revenue_delta': 0.50,  # Loan book growth
        },
        'persistence': {
            'eps':       0.40,  # Consistent earnings is king
            'revenue':   0.30,
            'direction': 0.30,
        },
    },
    'reit': {
        'health': {
            'dividend_yield': 0.30,  # Distribution is the point
            'eps_stability':  0.30,  # Stable income stream
            'de_ratio':       0.25,  # Regulated leverage limit
            'roe':            0.15,
        },
        'improvement': {
            'revenue_delta': 0.45,  # Occupancy/rental rate proxy
            'dps_delta':     0.30,  # Distribution growth
            'eps_delta':     0.25,
        },
        'persistence': {
            'dps':     0.35,  # Dividend persistence is THE signal
            'revenue': 0.35,
            'eps':     0.30,
        },
    },
    'holding': {
        'health': {
            'eps_stability': 0.35,  # Diversification should reduce volatility
            'roe':           0.25,  # Capital allocation efficiency
            'pb':            0.25,  # NAV discount = key metric
            'de_ratio':      0.15,
        },
        'improvement': {
            'eps_delta':     0.45,  # Primary signal for conglomerates
            'revenue_delta': 0.35,
            'roe_delta':     0.20,
        },
        'persistence': {
            'direction': 0.35,  # Consistency across segments
            'eps':       0.35,
            'revenue':   0.30,
        },
    },
    'property': {
        'health': {
            'de_ratio':      0.30,  # Capital-intensive; leverage is critical
            'eps_stability': 0.30,  # Cyclical — stability is valuable
            'ni_margin':     0.20,  # Margin quality (capped)
            'roe':           0.20,
        },
        'improvement': {
            'revenue_delta': 0.50,  # Project launches/completions
            'eps_delta':     0.50,
        },
        'persistence': {
            'revenue':   0.40,  # Revenue persistence critical (cyclical)
            'eps':       0.30,
            'direction': 0.30,
        },
    },
    'industrial': {
        'health': {
            'eps_stability': 0.35,  # Predictable earners valued higher
            'roe':           0.30,
            'de_ratio':      0.20,
            'ni_margin':     0.15,  # Supporting signal (capped)
        },
        'improvement': {
            'eps_delta':     0.45,
            'revenue_delta': 0.35,
            'roe_delta':     0.20,
        },
        'persistence': {
            'direction': 0.35,
            'revenue':   0.35,
            'eps':       0.30,
        },
    },
    'mining': {
        'health': {
            'de_ratio':      0.40,  # Survival metric in commodity downturns
            'roe':           0.25,
            'eps_stability': 0.20,  # Lower weight: volatility is structural
            'ni_margin':     0.15,  # Supporting signal (capped)
        },
        'improvement': {
            'revenue_delta': 0.55,  # Commodity price proxy — primary signal
            'eps_delta':     0.45,
        },
        'persistence': {
            'direction': 0.40,  # Direction matters more than streak
            'revenue':   0.30,
            'eps':       0.30,
        },
    },
    'services': {
        'health': {
            'eps_stability': 0.35,
            'roe':           0.30,
            'de_ratio':      0.20,
            'ni_margin':     0.15,
        },
        'improvement': {
            'eps_delta':     0.45,
            'revenue_delta': 0.35,
            'roe_delta':     0.20,
        },
        'persistence': {
            'direction': 0.35,
            'revenue':   0.35,
            'eps':       0.30,
        },
    },
}
# 'services' is also the fallback for any unrecognised group
SECTOR_SCORING_CONFIG['general'] = SECTOR_SCORING_CONFIG['services']
