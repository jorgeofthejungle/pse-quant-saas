# ============================================================
# alert_engine.py — Real-Time PSE Edge Disclosure & Price Alerts
# PSE Quant SaaS — Phase 4
# ============================================================
# Three checks per run:
#   1. Price alerts   — stocks at or below their MoS buy price
#   2. Dividend alerts — new cash dividend declarations on PSE Edge
#   3. Earnings alerts — new annual/quarterly filings on PSE Edge
#
# Each unique disclosure is stored in the `disclosures` DB table
# so it is only alerted once (dedup by unique URL key).
#
# Usage:
#   py alerts/alert_engine.py --dry-run          # detect, no Discord
#   py alerts/alert_engine.py --check price      # one check type only
# ============================================================

import re
import sys
import time
import argparse
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT / 'engine'))
sys.path.insert(0, str(ROOT / 'discord'))
sys.path.insert(0, str(ROOT / 'scraper'))
sys.path.insert(0, str(ROOT))

import database as db
from config import SCRAPE_DELAY_SECS, PSE_EDGE_BASE_URL

try:
    from scraper.pse_session import (make_session, _get,
                                     DIVIDENDS_LIST_URL,
                                     FIN_REPORTS_FORM, FIN_REPORTS_SEARCH)
    from scraper.pse_lookup  import lookup_company_info
except ImportError:
    from pse_session import (make_session, _get,
                              DIVIDENDS_LIST_URL,
                              FIN_REPORTS_FORM, FIN_REPORTS_SEARCH)
    from pse_lookup  import lookup_company_info

from publisher import WEBHOOKS, send_dividend_alert, send_price_alert, send_earnings_alert
from mos import calc_ddm, calc_eps_pe, calc_mos_price, calc_two_stage_ddm, calc_hybrid_intrinsic


# ── Disclosure DB helpers ─────────────────────────────────────

def _get_seen_urls(ticker: str) -> set:
    """Returns URL keys already stored for this ticker (dedup guard)."""
    conn = db.get_connection()
    rows = conn.execute(
        "SELECT url FROM disclosures WHERE ticker = ?", (ticker,)
    ).fetchall()
    conn.close()
    return {r['url'] for r in rows if r['url']}


def _save_disclosure(ticker: str, date: str, disc_type: str,
                     title: str, url: str):
    """Saves one disclosure record. Silently ignores duplicates."""
    conn = db.get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO disclosures (ticker, date, type, title, url) "
        "VALUES (?, ?, ?, ?, ?)",
        (ticker, date, disc_type, title, url),
    )
    conn.commit()
    conn.close()


def _claim_disclosure(ticker: str, date: str, disc_type: str,
                      title: str, url: str) -> bool:
    """
    Atomically inserts a disclosure record.
    Returns True if the record was new (this process claimed it),
    False if it already existed (duplicate — skip the send).
    Using INSERT OR IGNORE + rowcount prevents duplicate sends even
    when two scheduler processes run at the same time.
    """
    conn = db.get_connection()
    cur = conn.execute(
        "INSERT OR IGNORE INTO disclosures (ticker, date, type, title, url) "
        "VALUES (?, ?, ?, ?, ?)",
        (ticker, date, disc_type, title, url),
    )
    conn.commit()
    inserted = cur.rowcount > 0
    conn.close()
    return inserted


def _get_ranked_tickers() -> list:
    """
    Returns all tickers from the most recent scores run joined with
    their current price. Each row includes all three portfolio scores.
    """
    conn = db.get_connection()
    latest = conn.execute(
        "SELECT MAX(run_date) AS run_date FROM scores"
    ).fetchone()
    if not latest or not latest['run_date']:
        conn.close()
        return []

    rows = conn.execute("""
        SELECT s.ticker, st.name,
               s.pure_dividend_score,   s.pure_dividend_rank,
               s.dividend_growth_score, s.dividend_growth_rank,
               s.value_score,           s.value_rank,
               p.close AS current_price
        FROM scores s
        JOIN stocks st ON s.ticker = st.ticker
        LEFT JOIN (
            SELECT ticker, close FROM prices
            WHERE (ticker, date) IN (
                SELECT ticker, MAX(date) FROM prices GROUP BY ticker
            )
        ) p ON s.ticker = p.ticker
        WHERE s.run_date = ?
    """, (latest['run_date'],)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── 1. Price Alerts ───────────────────────────────────────────

def check_price_alerts(dry_run: bool = False) -> int:
    """
    Compares current price to MoS buy price for each ranked stock.
    Sends a price alert when current_price <= mos_price.
    Only checks stocks ranked in the top 15 per portfolio.
    Returns the number of alerts sent (or detected in dry-run).
    """
    alerts_url = WEBHOOKS.get('alerts', '')
    ranked     = _get_ranked_tickers()
    if not ranked:
        print("  [price_alerts] No ranked stocks found — skipping.")
        return 0

    sent  = 0
    today = datetime.now().strftime('%Y-%m-%d')

    PORTFOLIO_COLS = [
        ('pure_dividend',   'pure_dividend_score',   'pure_dividend_rank'),
        ('dividend_growth', 'dividend_growth_score', 'dividend_growth_rank'),
        ('value',           'value_score',           'value_rank'),
    ]

    for row in ranked:
        ticker        = row['ticker']
        current_price = row.get('current_price')
        if not current_price or current_price <= 0:
            continue

        fins     = db.get_financials(ticker, years=5)
        dps_last = fins[0].get('dps') if fins else None
        eps_list = [f['eps'] for f in fins if f.get('eps') is not None]

        ddm_val, _ = calc_ddm(dps_last, None)
        eps_val, _ = calc_eps_pe(eps_list[:3])

        for portfolio_type, score_col, rank_col in PORTFOLIO_COLS:
            score = row.get(score_col)
            rank  = row.get(rank_col)
            if score is None or rank is None or rank > 15:
                continue

            if portfolio_type == 'pure_dividend':
                iv = ddm_val
            elif portfolio_type == 'dividend_growth':
                iv, _ = calc_two_stage_ddm(dps_last, None)
            else:
                iv, _ = calc_hybrid_intrinsic(ddm_val, eps_val, None)

            if not iv or iv <= 0:
                continue
            mos_price = calc_mos_price(iv, portfolio_type)
            if not mos_price or current_price > mos_price:
                continue

            url_key = f"PRICE_ALERT:{portfolio_type}:{today}"

            # Atomically claim this alert slot before sending.
            # If another process already claimed it, skip (prevents duplicates).
            if dry_run:
                if url_key in _get_seen_urls(ticker):
                    continue
            else:
                if not _claim_disclosure(ticker, today, 'price_alert',
                                         f"Price at MoS: {portfolio_type}", url_key):
                    continue

            print(f"  [price_alert] {ticker} ({portfolio_type}): "
                  f"PHP{current_price:.2f} <= MoS PHP{mos_price:.2f}")
            if not dry_run and alerts_url:
                send_price_alert(
                    webhook_url=alerts_url, ticker=ticker,
                    company=row.get('name', ticker),
                    current_price=current_price, mos_price=mos_price,
                    intrinsic_value=iv, portfolio_type=portfolio_type,
                    score=score,
                )
            sent += 1

    return sent


# ── 2. Dividend Alerts ────────────────────────────────────────

def _fetch_dividend_declarations(session, cmpy_id: str) -> list:
    """
    Fetches individual cash dividend rows from PSE Edge.
    Returns list of {ex_date, record_date, pay_date, dps, url_key}.
    """
    from bs4 import BeautifulSoup
    _get(session,
         f'{PSE_EDGE_BASE_URL}/companyPage/dividends_and_rights_form.do',
         params={'cmpy_id': cmpy_id})
    time.sleep(SCRAPE_DELAY_SECS)
    resp = _get(session, DIVIDENDS_LIST_URL,
                params={'DividendsOrRights': 'Dividends', 'cmpy_id': cmpy_id})
    if not resp or len(resp.text) < 300:
        return []

    soup    = BeautifulSoup(resp.text, 'lxml')
    results = []
    for row in soup.find_all('tr'):
        cells = row.find_all('td')
        if len(cells) < 6:
            continue
        if 'cash' not in cells[1].get_text(strip=True).lower():
            continue
        rate_match = re.search(r'[\d.]+', cells[2].get_text(strip=True))
        if not rate_match:
            continue
        dps = float(rate_match.group())
        if not (0.001 < dps < 200):
            continue
        ex_date = cells[3].get_text(strip=True)
        if not ex_date:
            continue
        results.append({
            'ex_date':     ex_date,
            'record_date': cells[4].get_text(strip=True),
            'pay_date':    cells[5].get_text(strip=True),
            'dps':         dps,
            'url_key':     f"DIV:{ex_date}:{round(dps, 4)}",
        })
    return results


def _get_alert_baseline_date(ticker: str) -> str | None:
    """
    Returns the stored baseline date for a ticker's dividend alerts.
    Dividends with ex-dates on or before this date are treated as
    historical (no alert). Returns None if no baseline is set yet.
    """
    conn = db.get_connection()
    row  = conn.execute(
        "SELECT value FROM settings WHERE key = ?",
        (f'div_baseline:{ticker}',)
    ).fetchone()
    conn.close()
    return row['value'] if row else None


def _set_alert_baseline_date(ticker: str, date_str: str):
    """Saves the dividend alert baseline date for a ticker."""
    now  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = db.get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
        (f'div_baseline:{ticker}', date_str, now)
    )
    conn.commit()
    conn.close()


def _parse_ex_date(ex_date_str: str) -> str | None:
    """
    Normalises a PSE Edge ex-date string to YYYY-MM-DD.
    PSE Edge formats: 'MM/DD/YYYY', 'MMM DD, YYYY', 'YYYY-MM-DD'.
    Returns None if parsing fails.
    """
    for fmt in ('%m/%d/%Y', '%b %d, %Y', '%Y-%m-%d', '%B %d, %Y'):
        try:
            return datetime.strptime(ex_date_str.strip(), fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


def check_dividend_alerts(dry_run: bool = False) -> int:
    """
    Checks PSE Edge dividend declarations for all ranked tickers.
    Uses a per-ticker baseline date (stored in settings table) to
    distinguish pre-existing history from genuinely new declarations.
    Dividends with ex-dates strictly after the baseline date are alerted.
    Returns the number of new alerts sent.
    """
    alerts_url = WEBHOOKS.get('alerts', '')
    session    = make_session()
    sent       = 0
    today      = datetime.now().strftime('%Y-%m-%d')

    for row in _get_ranked_tickers():
        ticker = row['ticker']
        info   = lookup_company_info(session, ticker)
        if not info:
            time.sleep(SCRAPE_DELAY_SECS)
            continue

        divs = _fetch_dividend_declarations(session, info['cmpy_id'])
        if not divs:
            time.sleep(SCRAPE_DELAY_SECS)
            continue

        baseline = _get_alert_baseline_date(ticker)
        seen     = _get_seen_urls(ticker)

        if baseline is None:
            # First time we've ever checked this ticker.
            # Set baseline = today. Any dividend declared before today
            # is historical. We save it as 'seen' but never alert.
            # Dividends declared AFTER today will alert on next check.
            _set_alert_baseline_date(ticker, today)
            for entry in divs[:6]:
                _save_disclosure(ticker, entry['ex_date'], 'dividend_seen',
                                 f"Baseline DPS {entry['dps']}", entry['url_key'])
            print(f"  [div_alert] {ticker}: baseline set ({len(divs[:6])} "
                  f"historical dividends recorded, no alert sent).")
            time.sleep(SCRAPE_DELAY_SECS)
            continue

        for entry in divs[:6]:
            url_key = entry['url_key']
            if url_key in seen:
                continue  # already alerted or already baseline

            ex_date_norm = _parse_ex_date(entry['ex_date'])
            if ex_date_norm and ex_date_norm <= baseline:
                # Dividend existed before our monitoring started — save as seen,
                # do not alert. This handles the JFC-style historical dividend.
                _save_disclosure(ticker, entry['ex_date'], 'dividend_seen',
                                 f"Pre-baseline DPS {entry['dps']}", url_key)
                continue

            # Genuinely new dividend — ex-date is after our baseline.
            print(f"  [div_alert] NEW: {ticker}  "
                  f"DPS=PHP{entry['dps']:.4f}  ex={entry['ex_date']}")
            if not dry_run and alerts_url:
                send_dividend_alert(
                    webhook_url=alerts_url, ticker=ticker,
                    company=info.get('name', ticker),
                    dps=entry['dps'], ex_date=entry['ex_date'],
                    record_date=entry['record_date'],
                    pay_date=entry['pay_date'],
                )
            _save_disclosure(ticker, entry['ex_date'], 'dividend',
                             f"Cash div PHP{entry['dps']:.4f} ex {entry['ex_date']}",
                             url_key)
            sent += 1

        time.sleep(SCRAPE_DELAY_SECS)
    return sent


# ── 3. Earnings Alerts ────────────────────────────────────────

def _fetch_recent_filings(session, cmpy_id: str, from_date: str) -> list:
    """
    Returns annual/quarterly report filings on PSE Edge since from_date.
    Each entry: {edge_no, date, title, url_key}.
    """
    from bs4 import BeautifulSoup
    _get(session, FIN_REPORTS_FORM, params=None)
    time.sleep(SCRAPE_DELAY_SECS)
    resp = _get(session, FIN_REPORTS_SEARCH,
                params={'companyId': cmpy_id, 'tmplNm': '',
                        'fromDate': from_date, 'toDate': '12-31-2026',
                        'sortType': 'D', 'pageNo': '1'})
    if not resp or len(resp.text) < 500:
        return []

    soup    = BeautifulSoup(resp.text, 'lxml')
    results = []
    keywords = ['annual', '17-1', 'audited', 'quarterly', '17-q', '17q',
                'interim', 'earnings']
    for row in soup.find_all('tr'):
        cells = row.find_all('td')
        if len(cells) < 5:
            continue
        tmpl = cells[1].get_text(strip=True)
        date = cells[3].get_text(strip=True)
        rnum = cells[4].get_text(strip=True)
        if not any(k in tmpl.lower() for k in keywords):
            continue
        edge_no = ''
        for tag in row.find_all(onclick=True):
            m = re.search(r"openPopup\('([a-f0-9]+)'\)",
                          tag.get('onclick', ''))
            if m:
                edge_no = m.group(1)
                break
        if edge_no:
            results.append({
                'edge_no': edge_no,
                'date':    date,
                'title':   f"{tmpl} ({rnum})",
                'url_key': f"FILING:{edge_no}",
            })
    return results


def check_earnings_alerts(dry_run: bool = False,
                           lookback_days: int = 30) -> int:
    """
    Checks PSE Edge for new annual/quarterly filings in the last
    lookback_days for all ranked tickers. Only alerts on unseen filings.
    Returns the number of alerts sent.
    """
    alerts_url = WEBHOOKS.get('alerts', '')
    session    = make_session()
    sent       = 0
    from_date  = (datetime.now() - timedelta(days=lookback_days)
                  ).strftime('%m-%d-%Y')

    for row in _get_ranked_tickers():
        ticker = row['ticker']
        info   = lookup_company_info(session, ticker)
        if not info:
            time.sleep(SCRAPE_DELAY_SECS)
            continue

        filings = _fetch_recent_filings(session, info['cmpy_id'], from_date)
        seen    = _get_seen_urls(ticker)

        for filing in filings:
            if filing['url_key'] in seen:
                continue
            is_q = any(k in filing['title'].lower()
                       for k in ['quarterly', '17-q', '17q', 'interim'])
            label = 'Quarterly' if is_q else 'Annual'
            print(f"  [earnings_alert] NEW: {ticker}  {label}  {filing['date']}")

            fins     = db.get_financials(ticker, years=2)
            ni_curr  = fins[0].get('net_income') if fins else None
            ni_prior = fins[1].get('net_income') if len(fins) > 1 else None
            eps      = fins[0].get('eps')         if fins else None

            if not dry_run and alerts_url and ni_curr is not None and eps is not None:
                send_earnings_alert(
                    webhook_url=alerts_url, ticker=ticker,
                    company=info.get('name', ticker),
                    period=f"{label} — {filing['date']}",
                    net_income=ni_curr,
                    net_income_prior=ni_prior or ni_curr,
                    eps=eps,
                )
            _save_disclosure(ticker, filing['date'],
                             'quarterly' if is_q else 'annual',
                             filing['title'], filing['url_key'])
            sent += 1

        time.sleep(SCRAPE_DELAY_SECS)
    return sent


# ── Main Entry Point ──────────────────────────────────────────

def run_alert_check(dry_run: bool = False):
    """Runs all three checks. In dry-run mode, prints without sending."""
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    print(f"\n{'='*55}")
    print(f"  PSE QUANT SAAS — Alert Check  {now}")
    if dry_run:
        print("  [DRY-RUN — no Discord messages will be sent]")
    print(f"{'='*55}")

    if not WEBHOOKS.get('alerts') and not dry_run:
        print("\n  WARNING: DISCORD_WEBHOOK_ALERTS not set in .env — alerts "
              "will be detected but not delivered.")

    print("\n[1/3]  Checking price alerts...")
    try:
        n = check_price_alerts(dry_run=dry_run)
        print(f"  {n} price alert(s) {'detected' if dry_run else 'sent'}.")
    except Exception as e:
        print(f"  Price check failed: {e}")

    print("\n[2/3]  Checking dividend disclosures...")
    try:
        n = check_dividend_alerts(dry_run=dry_run)
        print(f"  {n} dividend alert(s) {'detected' if dry_run else 'sent'}.")
    except Exception as e:
        print(f"  Dividend check failed: {e}")

    print("\n[3/3]  Checking earnings filings...")
    try:
        n = check_earnings_alerts(dry_run=dry_run)
        print(f"  {n} earnings alert(s) {'detected' if dry_run else 'sent'}.")
    except Exception as e:
        print(f"  Earnings check failed: {e}")

    print(f"\n{'='*55}")
    print(f"  Alert check complete.  {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*55}\n")


# ── CLI ───────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='PSE Quant SaaS — Alert Engine',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'Examples:\n'
            '  py alerts/alert_engine.py --dry-run\n'
            '  py alerts/alert_engine.py --check price\n'
            '  py alerts/alert_engine.py --check dividend\n'
            '  py alerts/alert_engine.py --check earnings\n'
        )
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='Detect alerts but do not send to Discord')
    parser.add_argument('--check', choices=['price', 'dividend', 'earnings'],
                        help='Run one check type only (default: all)')
    args = parser.parse_args()

    db.init_db()

    if args.check == 'price':
        print(f"{check_price_alerts(dry_run=args.dry_run)} price alert(s).")
    elif args.check == 'dividend':
        print(f"{check_dividend_alerts(dry_run=args.dry_run)} dividend alert(s).")
    elif args.check == 'earnings':
        print(f"{check_earnings_alerts(dry_run=args.dry_run)} earnings alert(s).")
    else:
        run_alert_check(dry_run=args.dry_run)
