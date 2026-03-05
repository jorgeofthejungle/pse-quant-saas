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

# Daily alert check: every weekday at 6:30 AM
DAILY_ALERT_HOUR   = 6
DAILY_ALERT_MINUTE = 30

# ── PSE Edge Settings ──────────────────────────────────────
PSE_EDGE_BASE_URL   = 'https://edge.pse.com.ph'
SCRAPE_DELAY_SECS   = 3     # seconds between requests — be respectful
REQUEST_TIMEOUT     = 30    # seconds before a request times out
MAX_RETRIES         = 3     # number of retry attempts for failed requests

# ── Financial Model Settings ───────────────────────────────
# These match the values in mos.py — update both if you change them
PH_RISK_FREE_RATE   = 0.065   # PH 10-year T-bond rate (~6.5%)
EQUITY_RISK_PREMIUM = 0.050   # PSE equity risk premium (~5.0%)
DEFAULT_TARGET_PE   = 15.0    # Fair PE multiple for Philippine market
DDM_MAX_GROWTH_RATE = 0.07    # Cap on DDM dividend growth rate

# ── Data Lookback ──────────────────────────────────────────
YEARS_PREFERRED = 5   # Use 5 years of data when available
YEARS_MINIMUM   = 3   # Require at least 3 years; flag stocks with less
