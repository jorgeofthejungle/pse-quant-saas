# ============================================================
# disclosure_monitor.py — PSE Edge Feed Monitor (15-min polling)
# PSE Quant SaaS — Phase 9A
# ============================================================
# Polls three PSE Edge AJAX feeds every 15 minutes:
#   1. /announcements/search.ax     — dividends, M&A, corporate actions
#   2. /financialReports/search.ax  — earnings filings
#   3. /listingNotices/search.ax    — trading halts, suspensions
#
# Only alerts on disclosures from the top-ranked tickers.
# All sends are deduplicated via the disclosures DB table.
#
# Usage:
#   Called by scheduler every 15 minutes via run_disclosure_check()
#   CLI: py alerts/disclosure_monitor.py --dry-run
# ============================================================

import re
import sys
import time
import argparse
import threading
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT / 'discord'))
sys.path.insert(0, str(ROOT / 'scraper'))
sys.path.insert(0, str(ROOT))

import database as db
from config import PSE_EDGE_BASE_URL, SCRAPE_DELAY_SECS, REQUEST_TIMEOUT

try:
    from scraper.pse_session import make_session, _get
except ImportError:
    from pse_session import make_session, _get

from publisher import WEBHOOKS, send_dividend_alert, send_earnings_alert

# ── Feed URL constants ────────────────────────────────────────

ANNOUNCEMENTS_SEARCH  = f'{PSE_EDGE_BASE_URL}/announcements/search.ax'
FIN_REPORTS_SEARCH    = f'{PSE_EDGE_BASE_URL}/financialReports/search.ax'
LISTING_NOTICES_SEARCH = f'{PSE_EDGE_BASE_URL}/listingNotices/search.ax'

# ── Announcement keywords → alert categories ─────────────────

DIVIDEND_KEYWORDS = [
    'cash dividend', 'dividend declaration', 'declaration of dividend',
    'cash div', 'div declaration',
]
EARNINGS_KEYWORDS = [
    '17-1', '17-q', '17q', 'annual report', 'quarterly report',
    'audited financial', 'interim', 'earnings release',
]
CORPORATE_ACTION_KEYWORDS = [
    'merger', 'acquisition', 'rights offering', 'stock rights',
    'tender offer', 'business combination', 'disposal',
    'material transaction', 'major investment',
]
HALT_KEYWORDS = [
    'trading halt', 'suspension', 'trading suspension',
    'resumption of trading', 'delisting',
]
REGULATORY_KEYWORDS = [
    'sanction', 'penalty', 'violation', 'cease and desist',
    'show cause', 'fine',
]


# ── Material disclosure categories that warrant a rescore ────
# Dividends affect yield calculations; earnings bring new financials;
# corporate actions change the business itself. Trading halts do not.
_RESCORE_CATEGORIES = {'dividend', 'earnings', 'corporate_action'}

# Per-ticker cooldown: only one triggered rescore per ticker per 4 hours
_rescore_timestamps: dict[str, datetime] = {}
_rescore_cooldown_hours = 4


def _trigger_rescore_for_ticker(ticker: str, category: str, dry_run: bool = False):
    """
    If category is material and cooldown has passed, launches a full
    re-score pipeline in a background thread.

    Uses scheduler_jobs.run_daily_score() so the same dedup + change
    detection logic applies. A new pending_pdf.json is written if
    rankings shift — which run_daily_report() will pick up at 6 PM.
    """
    if category not in _RESCORE_CATEGORIES:
        return

    last = _rescore_timestamps.get(ticker)
    if last:
        elapsed_h = (datetime.now() - last).total_seconds() / 3600
        if elapsed_h < _rescore_cooldown_hours:
            print(f"  [disclosure_monitor] Rescore cooldown active for "
                  f"{ticker} ({elapsed_h:.1f}h < {_rescore_cooldown_hours}h) — skipped.")
            return

    _rescore_timestamps[ticker] = datetime.now()

    if dry_run:
        print(f"  [disclosure_monitor] [DRY-RUN] Would trigger rescore for "
              f"{ticker} ({category})")
        return

    print(f"  [disclosure_monitor] Material {category} from {ticker} — "
          f"triggering background rescore...")

    def _background_rescore():
        try:
            # Import here to avoid circular import at module load time
            sys.path.insert(0, str(ROOT))
            from scheduler_jobs import run_daily_score
            run_daily_score()
        except Exception as exc:
            print(f"  [disclosure_monitor] Triggered rescore failed: {exc}")

    t = threading.Thread(target=_background_rescore, daemon=True,
                         name=f'rescore_{ticker}')
    t.start()


# ── Dedup helpers (reuse patterns from alert_engine.py) ───────

def _claim_disclosure(ticker: str, date: str, disc_type: str,
                      title: str, url: str) -> bool:
    """Atomically claims a disclosure slot. Returns True if new."""
    conn = db.get_connection()
    cur  = conn.execute(
        "INSERT OR IGNORE INTO disclosures (ticker, date, type, title, url) "
        "VALUES (?, ?, ?, ?, ?)",
        (ticker, date, disc_type, title, url),
    )
    conn.commit()
    inserted = cur.rowcount > 0
    conn.close()
    return inserted


def _get_ranked_tickers_set() -> set:
    """Returns set of ranked tickers from the most recent scores run."""
    conn = db.get_connection()
    latest = conn.execute(
        "SELECT MAX(run_date) AS run_date FROM scores"
    ).fetchone()
    if not latest or not latest['run_date']:
        conn.close()
        return set()
    rows = conn.execute(
        "SELECT DISTINCT ticker FROM scores WHERE run_date = ?",
        (latest['run_date'],)
    ).fetchall()
    conn.close()
    return {r['ticker'] for r in rows}


def _get_ticker_name(ticker: str) -> str:
    """Returns company name for a ticker, falls back to ticker."""
    conn = db.get_connection()
    row  = conn.execute(
        "SELECT name FROM stocks WHERE ticker = ?", (ticker,)
    ).fetchone()
    conn.close()
    return row['name'] if row else ticker


# ── Feed Parsers ──────────────────────────────────────────────

def _parse_announcement_feed(session, lookback_hours: int = 2) -> list:
    """
    Polls PSE Edge announcements feed.
    Returns list of {ticker, date, title, form_type, edge_no, url_key}.
    Only returns entries from the last lookback_hours.
    """
    from bs4 import BeautifulSoup
    cutoff = datetime.now() - timedelta(hours=lookback_hours)

    params = {
        'method':      'getAnnouncements',
        'sortType':    'D',
        'pageNo':      '1',
        'tmplNm':      '',
        'companyName': '',
        'fromDate':    cutoff.strftime('%m-%d-%Y'),
        'toDate':      datetime.now().strftime('%m-%d-%Y'),
    }
    try:
        resp = _get(session, ANNOUNCEMENTS_SEARCH, params=params)
    except Exception:
        return []
    if not resp or len(resp.text) < 300:
        return []

    soup    = BeautifulSoup(resp.text, 'lxml')
    results = []
    for row in soup.find_all('tr'):
        cells = row.find_all('td')
        if len(cells) < 5:
            continue
        company   = cells[0].get_text(strip=True)
        tmpl      = cells[1].get_text(strip=True)
        pse_form  = cells[2].get_text(strip=True)
        date_str  = cells[3].get_text(strip=True)
        edge_no   = ''
        for tag in row.find_all(onclick=True):
            m = re.search(r"openPopup\('([a-f0-9]+)'\)", tag.get('onclick', ''))
            if m:
                edge_no = m.group(1)
                break
        if not company or not date_str or not edge_no:
            continue
        # Try to extract ticker from company name (format: "NAME (TICKER)")
        ticker_match = re.search(r'\(([A-Z0-9]+)\)', company)
        ticker = ticker_match.group(1) if ticker_match else None
        results.append({
            'ticker':    ticker,
            'company':   company,
            'date':      date_str,
            'title':     tmpl,
            'form_type': pse_form,
            'edge_no':   edge_no,
            'url_key':   f'ANN:{edge_no}',
        })
    return results


def _parse_financial_reports_feed(session, lookback_hours: int = 2) -> list:
    """
    Polls PSE Edge financial reports feed.
    Returns list of {ticker, date, title, edge_no, url_key}.
    """
    from bs4 import BeautifulSoup
    cutoff = datetime.now() - timedelta(hours=lookback_hours)

    params = {
        'method':    'getFinancialReports',
        'sortType':  'D',
        'pageNo':    '1',
        'tmplNm':    '',
        'fromDate':  cutoff.strftime('%m-%d-%Y'),
        'toDate':    datetime.now().strftime('%m-%d-%Y'),
    }
    try:
        resp = _get(session, FIN_REPORTS_SEARCH, params=params)
    except Exception:
        return []
    if not resp or len(resp.text) < 300:
        return []

    soup    = BeautifulSoup(resp.text, 'lxml')
    results = []
    for row in soup.find_all('tr'):
        cells = row.find_all('td')
        if len(cells) < 5:
            continue
        company  = cells[0].get_text(strip=True)
        tmpl     = cells[1].get_text(strip=True)
        date_str = cells[3].get_text(strip=True)
        edge_no  = ''
        for tag in row.find_all(onclick=True):
            m = re.search(r"openPopup\('([a-f0-9]+)'\)", tag.get('onclick', ''))
            if m:
                edge_no = m.group(1)
                break
        if not company or not date_str or not edge_no:
            continue
        ticker_match = re.search(r'\(([A-Z0-9]+)\)', company)
        ticker = ticker_match.group(1) if ticker_match else None
        results.append({
            'ticker':  ticker,
            'company': company,
            'date':    date_str,
            'title':   tmpl,
            'edge_no': edge_no,
            'url_key': f'FIN:{edge_no}',
        })
    return results


def _parse_listing_notices_feed(session, lookback_hours: int = 2) -> list:
    """
    Polls PSE Edge listing notices feed for trading halts/suspensions.
    Returns list of {date, title, notice_no, url_key}.
    Note: listing notices are exchange-wide, not per-ticker.
    """
    from bs4 import BeautifulSoup
    cutoff = datetime.now() - timedelta(hours=lookback_hours)

    params = {
        'method':   'getListingNotices',
        'sortType': 'D',
        'pageNo':   '1',
        'subject':  '',
        'fromDate': cutoff.strftime('%m-%d-%Y'),
        'toDate':   datetime.now().strftime('%m-%d-%Y'),
    }
    try:
        resp = _get(session, LISTING_NOTICES_SEARCH, params=params)
    except Exception:
        return []
    if not resp or len(resp.text) < 200:
        return []

    soup    = BeautifulSoup(resp.text, 'lxml')
    results = []
    for row in soup.find_all('tr'):
        cells = row.find_all('td')
        if len(cells) < 3:
            continue
        subject  = cells[0].get_text(strip=True)
        date_str = cells[1].get_text(strip=True)
        notice   = cells[2].get_text(strip=True)
        if not subject or not date_str:
            continue
        results.append({
            'ticker':    None,
            'date':      date_str,
            'title':     subject,
            'notice_no': notice,
            'url_key':   f'LN:{notice}:{date_str}',
        })
    return results


# ── Category classifier ───────────────────────────────────────

def _classify_announcement(title: str) -> str:
    """Returns alert category based on announcement title keywords."""
    t = title.lower()
    if any(k in t for k in DIVIDEND_KEYWORDS):
        return 'dividend'
    if any(k in t for k in EARNINGS_KEYWORDS):
        return 'earnings'
    if any(k in t for k in CORPORATE_ACTION_KEYWORDS):
        return 'corporate_action'
    if any(k in t for k in HALT_KEYWORDS):
        return 'trading_halt'
    if any(k in t for k in REGULATORY_KEYWORDS):
        return 'regulatory'
    return 'announcement'


# ── Discord embed builder for general disclosures ─────────────

def _send_disclosure_alert(webhook_url: str, ticker: str, company: str,
                            category: str, title: str, date: str):
    """Sends a formatted Discord embed for a new PSE Edge disclosure."""
    import requests as req

    CATEGORY_COLOUR = {
        'dividend':        0xF1C40F,   # gold
        'earnings':        0x3498DB,   # blue
        'corporate_action': 0xE67E22,  # orange
        'trading_halt':    0xE74C3C,   # red
        'regulatory':      0xE74C3C,   # red
        'announcement':    0x95A5A6,   # grey
    }
    CATEGORY_LABEL = {
        'dividend':         'Dividend Declaration',
        'earnings':         'Earnings Filing',
        'corporate_action': 'Corporate Action',
        'trading_halt':     'Trading Halt / Suspension',
        'regulatory':       'Regulatory Notice',
        'announcement':     'Company Announcement',
    }
    colour = CATEGORY_COLOUR.get(category, 0x95A5A6)
    label  = CATEGORY_LABEL.get(category, 'Disclosure')

    embed = {
        'title':       f'{ticker} — {label}',
        'description': title,
        'color':       colour,
        'fields': [
            {'name': 'Company',  'value': company,  'inline': True},
            {'name': 'Date',     'value': date,     'inline': True},
            {'name': 'Category', 'value': label,    'inline': True},
        ],
        'footer': {'text': 'PSE Edge disclosure feed — PSE Quant SaaS'},
        'timestamp': datetime.utcnow().isoformat() + 'Z',
    }
    try:
        req.post(webhook_url, json={'embeds': [embed]}, timeout=15)
    except Exception as e:
        print(f"  [disclosure_monitor] Discord send failed: {e}")


# ── Main monitor function ─────────────────────────────────────

def run_disclosure_check(dry_run: bool = False,
                          lookback_hours: int = 2) -> int:
    """
    Checks all three PSE Edge feeds for new disclosures affecting
    ranked tickers. Sends immediate Discord alerts for new findings.
    Returns the total number of alerts sent.
    """
    alerts_url   = WEBHOOKS.get('alerts', '')
    ranked_set   = _get_ranked_tickers_set()
    if not ranked_set:
        print("  [disclosure_monitor] No ranked tickers — skipping.")
        return 0

    session = make_session()
    today   = datetime.now().strftime('%Y-%m-%d')
    sent    = 0

    # ── 1. Announcements feed ─────────────────────────────────
    print("  [disclosure_monitor] Polling announcements feed...")
    try:
        announcements = _parse_announcement_feed(session, lookback_hours)
        time.sleep(SCRAPE_DELAY_SECS)
    except Exception as e:
        print(f"  [disclosure_monitor] Announcements feed error: {e}")
        announcements = []

    for ann in announcements:
        ticker = ann.get('ticker')
        if not ticker or ticker not in ranked_set:
            continue
        category = _classify_announcement(ann['title'])
        url_key  = ann['url_key']
        if not _claim_disclosure(ticker, today, category,
                                 ann['title'], url_key):
            continue
        print(f"  [disclosure_monitor] NEW {category.upper()}: "
              f"{ticker}  {ann['title'][:60]}")
        if not dry_run and alerts_url:
            _send_disclosure_alert(
                alerts_url, ticker,
                _get_ticker_name(ticker),
                category, ann['title'], ann['date'],
            )
        _trigger_rescore_for_ticker(ticker, category, dry_run=dry_run)
        sent += 1

    # ── 2. Financial reports feed ─────────────────────────────
    print("  [disclosure_monitor] Polling financial reports feed...")
    try:
        fin_reports = _parse_financial_reports_feed(session, lookback_hours)
        time.sleep(SCRAPE_DELAY_SECS)
    except Exception as e:
        print(f"  [disclosure_monitor] Financial reports feed error: {e}")
        fin_reports = []

    for rpt in fin_reports:
        ticker = rpt.get('ticker')
        if not ticker or ticker not in ranked_set:
            continue
        category = _classify_announcement(rpt['title'])
        if category not in ('earnings', 'announcement'):
            category = 'earnings'
        url_key = rpt['url_key']
        if not _claim_disclosure(ticker, today, category,
                                 rpt['title'], url_key):
            continue
        print(f"  [disclosure_monitor] NEW {category.upper()}: "
              f"{ticker}  {rpt['title'][:60]}")
        if not dry_run and alerts_url:
            _send_disclosure_alert(
                alerts_url, ticker,
                _get_ticker_name(ticker),
                category, rpt['title'], rpt['date'],
            )
        _trigger_rescore_for_ticker(ticker, category, dry_run=dry_run)
        sent += 1

    # ── 3. Listing notices feed (trading halts) ───────────────
    print("  [disclosure_monitor] Polling listing notices feed...")
    try:
        notices = _parse_listing_notices_feed(session, lookback_hours)
        time.sleep(SCRAPE_DELAY_SECS)
    except Exception as e:
        print(f"  [disclosure_monitor] Listing notices feed error: {e}")
        notices = []

    for notice in notices:
        category = _classify_announcement(notice['title'])
        if category not in ('trading_halt', 'regulatory'):
            continue  # skip non-critical listing notices
        # Extract ticker from notice title if possible
        ticker_match = re.search(r'\b([A-Z]{2,6})\b', notice['title'])
        ticker = ticker_match.group(1) if ticker_match else 'EXCHANGE'
        if ticker not in ranked_set and ticker != 'EXCHANGE':
            continue
        url_key = notice['url_key']
        ref_ticker = ticker if ticker in ranked_set else 'EXCHANGE'
        # Use a placeholder stock entry for exchange-wide notices
        if not _claim_disclosure(ref_ticker, today, category,
                                 notice['title'], url_key):
            continue
        print(f"  [disclosure_monitor] NEW {category.upper()}: "
              f"{notice['title'][:70]}")
        if not dry_run and alerts_url:
            _send_disclosure_alert(
                alerts_url, ref_ticker, notice['title'],
                category, notice['title'], notice['date'],
            )
        sent += 1

    return sent


# ── CLI ───────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='PSE Quant SaaS — Disclosure Feed Monitor',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'Examples:\n'
            '  py alerts/disclosure_monitor.py --dry-run\n'
            '  py alerts/disclosure_monitor.py --lookback 4\n'
        )
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='Detect disclosures but do not send to Discord')
    parser.add_argument('--lookback', type=int, default=2,
                        help='Hours to look back in feeds (default: 2)')
    args = parser.parse_args()

    db.init_db()

    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    print(f"\n{'='*55}")
    print(f"  PSE QUANT SAAS — Disclosure Monitor  {now}")
    if args.dry_run:
        print("  [DRY-RUN — no Discord messages will be sent]")
    print(f"{'='*55}\n")

    n = run_disclosure_check(dry_run=args.dry_run, lookback_hours=args.lookback)
    print(f"\n  {n} disclosure alert(s) {'detected' if args.dry_run else 'sent'}.")
    print(f"{'='*55}\n")
