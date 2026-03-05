# ============================================================
# publisher.py — Discord Delivery Module
# PSE Quant SaaS — Phase 2
# ============================================================
# Sends PDF reports and alert messages to Discord channels
# using webhooks. No Discord bot token required.
#
# Channels:
#   #pse-dividend  — Dividend portfolio reports + dividend alerts
#   #pse-value     — Value portfolio reports + earnings alerts
#   #pse-hybrid    — Hybrid portfolio reports
#   #pse-alerts    — Price alerts, re-score notices (all portfolios)
#
# Discord webhook file size limit: 8 MB
# If a PDF exceeds 8 MB, a text summary is sent instead.
# ============================================================

import os
import json
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Always load .env from the project root (two levels up from this file)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / '.env')

# ── Webhook URLs (loaded from .env) ───────────────────────
# Set these in your .env file at the project root:
#   DISCORD_WEBHOOK_DIVIDEND=https://discord.com/api/webhooks/...
#   DISCORD_WEBHOOK_VALUE=https://discord.com/api/webhooks/...
#   DISCORD_WEBHOOK_HYBRID=https://discord.com/api/webhooks/...
#   DISCORD_WEBHOOK_ALERTS=https://discord.com/api/webhooks/...

WEBHOOKS = {
    'pure_dividend':   os.getenv('DISCORD_WEBHOOK_DIVIDEND', ''),
    'dividend_growth': os.getenv('DISCORD_WEBHOOK_HYBRID',   ''),
    'value':           os.getenv('DISCORD_WEBHOOK_VALUE',    ''),
    'alerts':          os.getenv('DISCORD_WEBHOOK_ALERTS',   ''),
}

# ── Colour codes (Discord embed colours) ──────────────────
COLOUR_DIVIDEND = 0x27AE60   # green
COLOUR_VALUE    = 0x2980B9   # blue
COLOUR_HYBRID   = 0x8E44AD   # purple
COLOUR_ALERT    = 0xE74C3C   # red
COLOUR_INFO     = 0x1B4B6B   # navy

# ── Discord file size limit ────────────────────────────────
MAX_FILE_BYTES = 8 * 1024 * 1024   # 8 MB

PORTFOLIO_COLOURS = {
    'pure_dividend':   COLOUR_DIVIDEND,
    'dividend_growth': COLOUR_HYBRID,
    'value':           COLOUR_VALUE,
}

PORTFOLIO_EMOJI = {
    'pure_dividend':   '💰',
    'dividend_growth': '📈',
    'value':           '📊',
}

DISCLAIMER = (
    'For research and educational purposes only. '
    'Not investment advice. Always do your own due diligence.'
)


# ── Low-level send functions ───────────────────────────────

def _post_webhook(webhook_url: str, payload: dict) -> bool:
    """
    Sends a JSON payload (no file) to a Discord webhook.
    Returns True on success, False on failure.
    """
    try:
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=15,
        )
        if response.status_code in (200, 204):
            return True
        print(f"Discord error {response.status_code}: {response.text[:200]}")
        return False
    except requests.RequestException as e:
        print(f"Discord request failed: {e}")
        return False


def _post_webhook_with_file(
    webhook_url: str,
    file_path: str,
    payload: dict,
) -> bool:
    """
    Sends a Discord webhook with a file attachment.
    payload_json is sent alongside the file as multipart form data.
    Returns True on success, False on failure.
    """
    try:
        with open(file_path, 'rb') as f:
            files = {
                'file': (os.path.basename(file_path), f, 'application/pdf'),
            }
            data = {
                'payload_json': json.dumps(payload),
            }
            response = requests.post(
                webhook_url,
                data=data,
                files=files,
                timeout=30,
            )
        if response.status_code in (200, 204):
            return True
        print(f"Discord file upload error {response.status_code}: {response.text[:200]}")
        return False
    except requests.RequestException as e:
        print(f"Discord file upload failed: {e}")
        return False
    except FileNotFoundError:
        print(f"PDF not found: {file_path}")
        return False


# ── Public API ─────────────────────────────────────────────

def send_report(
    webhook_url:    str,
    pdf_path:       str,
    portfolio_type: str,
    ranked_stocks:  list,
    run_date:       str = None,
) -> bool:
    """
    Sends a portfolio PDF report to a Discord channel.

    Parameters:
        webhook_url     — Discord webhook URL for the target channel
        pdf_path        — Absolute path to the generated PDF file
        portfolio_type  — 'dividend', 'value', or 'hybrid'
        ranked_stocks   — List of scored stock dicts (from process_stocks)
        run_date        — Optional date string; defaults to today

    What gets sent:
        1. An embed with the top 5 ranked stocks (scores, key metrics, MoS)
        2. The PDF file as an attachment (if under 8 MB)
           If the PDF is too large, a text note is sent instead.

    Returns True if Discord accepted the message, False otherwise.
    """
    if run_date is None:
        run_date = datetime.now().strftime('%B %d, %Y')

    emoji      = PORTFOLIO_EMOJI.get(portfolio_type, '📋')
    colour     = PORTFOLIO_COLOURS.get(portfolio_type, COLOUR_INFO)
    port_upper = portfolio_type.upper()

    # ── Build the top-5 fields ──
    fields = []
    for i, stock in enumerate(ranked_stocks[:5]):
        sc        = stock.get('score', 0)
        ticker    = stock.get('ticker', '')
        mos_pct   = stock.get('mos_pct', None)
        mos_price = stock.get('mos_price', None)
        dy        = stock.get('dividend_yield', None)
        pe        = stock.get('pe', None)

        # Build the metric line depending on portfolio type
        if portfolio_type == 'pure_dividend':
            metric_line = f"Yield: {dy:.1f}%" if dy else "Yield: N/A"
        elif portfolio_type == 'dividend_growth':
            cagr = stock.get('dividend_cagr_5y', None)
            parts = []
            if dy:
                parts.append(f"Yield: {dy:.1f}%")
            if cagr:
                parts.append(f"CAGR: +{cagr:.1f}%/yr")
            metric_line = "  |  ".join(parts) if parts else "N/A"
        elif portfolio_type == 'value':
            metric_line = f"P/E: {pe:.1f}×" if pe else "P/E: N/A"
        else:
            metric_line = "N/A"

        mos_line = (
            f"MoS: {mos_pct:.1f}%  |  Buy ≤ ₱{mos_price:.2f}"
            if mos_pct is not None and mos_price
            else "MoS: N/A"
        )

        grade_str = (
            'A — STRONG' if sc >= 80 else
            'B — GOOD'   if sc >= 65 else
            'C — FAIR'   if sc >= 50 else
            'D — WEAK'
        )

        fields.append({
            'name':   f"#{i+1}  {ticker}  —  {sc}/100  [{grade_str}]",
            'value':  f"{metric_line}\n{mos_line}",
            'inline': False,
        })

    # ── Build the embed ──
    embed = {
        'title':       f"{emoji}  PSE {port_upper} PORTFOLIO REPORT",
        'description': f"**Run date:** {run_date}\n**Stocks ranked:** {len(ranked_stocks)}",
        'color':       colour,
        'fields':      fields,
        'footer': {
            'text': DISCLAIMER,
        },
    }

    payload = {'embeds': [embed]}

    # ── Check file size ──
    if os.path.exists(pdf_path):
        file_size = os.path.getsize(pdf_path)

        if file_size <= MAX_FILE_BYTES:
            print(f"Sending {portfolio_type} report to Discord with PDF attachment...")
            success = _post_webhook_with_file(webhook_url, pdf_path, payload)
        else:
            # File too large — send embed only with a note
            size_mb = file_size / (1024 * 1024)
            embed['fields'].append({
                'name':   '⚠️  PDF Not Attached',
                'value':  (
                    f"The report PDF is {size_mb:.1f} MB — above Discord's 8 MB limit. "
                    f"The file is saved locally at:\n`{pdf_path}`"
                ),
                'inline': False,
            })
            print(
                f"PDF too large ({size_mb:.1f} MB) — "
                f"sending embed only, no attachment."
            )
            success = _post_webhook(webhook_url, payload)
    else:
        # PDF not found — send embed only
        embed['fields'].append({
            'name':   '⚠️  PDF Not Found',
            'value':  f"Expected at: `{pdf_path}`",
            'inline': False,
        })
        print(f"PDF not found at {pdf_path} — sending embed only.")
        success = _post_webhook(webhook_url, payload)

    if success:
        print(f"Discord delivery complete: #{portfolio_type} report sent.")
    return success


def send_dividend_alert(
    webhook_url: str,
    ticker:      str,
    company:     str,
    dps:         float,
    ex_date:     str,
    record_date: str,
    pay_date:    str,
    portfolio_score: float = None,
) -> bool:
    """
    Sends a dividend declaration alert.

    Triggered when PSE Edge publishes a new dividend announcement.

    Parameters:
        dps          — Dividend per share (in ₱)
        ex_date      — Ex-dividend date string
        record_date  — Record date string
        pay_date     — Payment date string
        portfolio_score — Current dividend score for this stock (optional)
    """
    score_line = (
        f"\n**Current dividend score:** {portfolio_score}/100"
        if portfolio_score is not None else ''
    )

    embed = {
        'title':       f"🔔  Dividend Declaration — {ticker}",
        'description': (
            f"**{company}** has declared a cash dividend.\n"
            f"{score_line}"
        ),
        'color':       COLOUR_DIVIDEND,
        'fields': [
            {
                'name':   'Dividend Per Share',
                'value':  f"₱{dps:.4f}",
                'inline': True,
            },
            {
                'name':   'Ex-Date',
                'value':  ex_date,
                'inline': True,
            },
            {
                'name':   'Record Date',
                'value':  record_date,
                'inline': True,
            },
            {
                'name':   'Payment Date',
                'value':  pay_date,
                'inline': True,
            },
        ],
        'footer': {
            'text': DISCLAIMER,
        },
    }

    return _post_webhook(webhook_url, {'embeds': [embed]})


def send_price_alert(
    webhook_url:    str,
    ticker:         str,
    company:        str,
    current_price:  float,
    mos_price:      float,
    intrinsic_value: float,
    portfolio_type: str,
    score:          float,
) -> bool:
    """
    Sends an alert when a stock's price drops at or below its MoS buy price.

    This is a factual price observation — not a recommendation.
    """
    gap_pct = ((mos_price - current_price) / mos_price) * 100

    embed = {
        'title':       f"📉  Price Alert — {ticker}  ({portfolio_type.upper()})",
        'description': (
            f"**{company}** is now trading AT OR BELOW the calculated "
            f"Margin of Safety buy price.\n\n"
            f"This is a mathematical observation, not a recommendation."
        ),
        'color':       COLOUR_ALERT,
        'fields': [
            {
                'name':   'Current Price',
                'value':  f"₱{current_price:.2f}",
                'inline': True,
            },
            {
                'name':   'MoS Buy Price',
                'value':  f"₱{mos_price:.2f}",
                'inline': True,
            },
            {
                'name':   'Intrinsic Value',
                'value':  f"₱{intrinsic_value:.2f}",
                'inline': True,
            },
            {
                'name':   'Price vs MoS Price',
                'value':  f"{gap_pct:.1f}% below MoS threshold",
                'inline': True,
            },
            {
                'name':   f'{portfolio_type.upper()} Score',
                'value':  f"{score}/100",
                'inline': True,
            },
        ],
        'footer': {
            'text': DISCLAIMER,
        },
    }

    return _post_webhook(webhook_url, {'embeds': [embed]})


def send_earnings_alert(
    webhook_url:      str,
    ticker:           str,
    company:          str,
    period:           str,
    net_income:       float,
    net_income_prior: float,
    eps:              float,
    disclosure_url:   str = None,
) -> bool:
    """
    Sends an alert when new earnings data is filed on PSE Edge.

    Parameters:
        period           — e.g. "Q3 2024" or "FY 2024"
        net_income       — Net income in millions (₱M)
        net_income_prior — Prior period net income for YoY comparison
        eps              — Earnings per share
        disclosure_url   — Link to the PSE Edge filing (optional)
    """
    yoy_change = ((net_income - net_income_prior) / abs(net_income_prior)) * 100 \
        if net_income_prior and net_income_prior != 0 else None

    yoy_str = f"{yoy_change:+.1f}% YoY" if yoy_change is not None else "YoY N/A"
    direction = "▲" if (yoy_change or 0) >= 0 else "▼"

    fields = [
        {
            'name':   'Period',
            'value':  period,
            'inline': True,
        },
        {
            'name':   'Net Income',
            'value':  f"₱{net_income:,.1f}M  {direction} {yoy_str}",
            'inline': True,
        },
        {
            'name':   'EPS',
            'value':  f"₱{eps:.2f}",
            'inline': True,
        },
    ]

    if disclosure_url:
        fields.append({
            'name':   'Filing',
            'value':  f"[View on PSE Edge]({disclosure_url})",
            'inline': False,
        })

    embed = {
        'title':       f"⚠️  Earnings Filed — {ticker}",
        'description': (
            f"**{company}** has filed new earnings results on PSE Edge.\n"
            f"Scores will be updated on the next scheduled run."
        ),
        'color':       COLOUR_INFO,
        'fields':      fields,
        'footer': {
            'text': DISCLAIMER,
        },
    }

    return _post_webhook(webhook_url, {'embeds': [embed]})


def send_rescore_notice(
    webhook_url:    str,
    portfolio_type: str,
    changes:        list,
) -> bool:
    """
    Sends a notice when new data triggers a re-score and rank changes.

    Parameters:
        changes — list of dicts: [
            {'ticker': 'BDO', 'old_rank': 4, 'new_rank': 2,
             'old_score': 68.5, 'new_score': 74.2},
            ...
        ]
    """
    emoji  = PORTFOLIO_EMOJI.get(portfolio_type, '📋')
    colour = PORTFOLIO_COLOURS.get(portfolio_type, COLOUR_INFO)

    fields = []
    for c in changes[:10]:   # Discord embed field limit
        old_r = c.get('old_rank', '?')
        new_r = c.get('new_rank', '?')
        arrow = '▲' if new_r < old_r else '▼'
        fields.append({
            'name':   f"{arrow}  {c['ticker']}",
            'value':  (
                f"Rank: #{old_r} → #{new_r}\n"
                f"Score: {c.get('old_score', '?'):.1f} → {c.get('new_score', '?'):.1f}"
            ),
            'inline': True,
        })

    embed = {
        'title':       f"{emoji}  Re-Score Complete — {portfolio_type.upper()}",
        'description': (
            f"New financial data triggered a re-score. "
            f"**{len(changes)} stock(s)** changed rank."
        ),
        'color':       colour,
        'fields':      fields,
        'footer': {
            'text': DISCLAIMER,
        },
    }

    return _post_webhook(webhook_url, {'embeds': [embed]})


def send_opportunistic_alert(
    ticker: str,
    company_name: str,
    summary: str,
    webhook_url: str = None,
) -> bool:
    """
    Sends an opportunistic watch alert to the #pse-alerts channel.
    Called when sentiment_engine flags a stock with opportunistic_flag=1.

    Parameters:
        ticker       — PSE ticker symbol
        company_name — Full company name
        summary      — 1-2 sentence sentiment summary from Claude Haiku
        webhook_url  — Override URL; defaults to DISCORD_WEBHOOK_ALERTS env var
    """
    url = webhook_url or WEBHOOKS.get('alerts', '')
    if not url:
        print("[publisher] DISCORD_WEBHOOK_ALERTS not set — skipping opportunistic alert")
        return False

    payload = {
        'embeds': [{
            'title': f"Opportunistic Watch: {ticker}",
            'description': (
                f"**{company_name}** ({ticker}) has been flagged based on recent news.\n\n"
                f"{summary}\n\n"
                f"*{DISCLAIMER}*"
            ),
            'color': 0x27AE60,   # green
            'footer': {
                'text': (
                    'PSE Quant SaaS — Sentiment is informational only. '
                    'Not a buy/sell recommendation.'
                )
            },
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }]
    }
    success = _post_webhook(url, payload)
    if success:
        print(f"[publisher] Opportunistic alert sent for {ticker}")
    return success


def test_webhook(webhook_url: str, channel_name: str) -> bool:
    """
    Sends a simple test message to verify the webhook URL works.
    Call this once after setting up each webhook in config.py.
    """
    payload = {
        'content': (
            f"✅  PSE Quant SaaS webhook connected successfully.\n"
            f"Channel: **{channel_name}**\n"
            f"Reports and alerts for this portfolio will appear here."
        )
    }
    success = _post_webhook(webhook_url, payload)
    if success:
        print(f"Webhook test passed: {channel_name}")
    else:
        print(f"Webhook test FAILED: {channel_name} — check the URL in .env")
    return success
