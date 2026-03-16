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
    'pure_dividend':   '',   # paste #pse-dividend webhook URL here
    'dividend_growth': '',   # paste #pse-hybrid webhook URL here
    'value':           '',   # paste #pse-value webhook URL here
    'alerts':          '',   # paste #pse-alerts webhook URL here (price/earnings alerts)
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

# ── Weekly Full Financial Scrape ───────────────────────────
WEEKLY_SCRAPE_DAY  = 'sun'
WEEKLY_SCRAPE_HOUR = 22    # 10:00 PM PHT — after-hours, before Monday market

# ── Stale Data Detection ───────────────────────────────────
# If a stock's latest price is older than WARN days, print a warning but
# still allow scoring.  If older than BLOCK days, the stock is hard-blocked
# from scoring (likely suspended or delisted).
STALE_PRICE_WARN_DAYS  = 30
STALE_PRICE_BLOCK_DAYS = 90

# How many days without a PSE Edge scrape before a ticker is auto-marked
# as 'suspended' during the weekly scrape comparison.
STALE_SCRAPE_SUSPEND_DAYS = 14

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
