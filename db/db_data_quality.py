# ============================================================
# db_data_quality.py — Financial Data Quality Auditor
# PSE Quant SaaS
# ============================================================
# Checks the database for suspicious or inconsistent values.
# Run: py db/db_data_quality.py
# Run with ticker filter: py db/db_data_quality.py --ticker LFM
# ============================================================

import sys
import sqlite3
import argparse
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'db'))

from db_connection import DB_PATH


def run_audit(ticker_filter: str = None) -> list[dict]:
    """
    Runs all data quality checks and returns a list of issue dicts.
    Each issue has: ticker, year, check, severity, detail, suggested_action
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    current_year = datetime.date.today().year

    issues = []

    # ── 1. DPS cross-checks ──────────────────────────────────
    where = f'AND f.ticker = "{ticker_filter}"' if ticker_filter else ''
    rows = conn.execute(f"""
        SELECT f.ticker, f.year, f.dps, f.eps, f.revenue, f.net_income,
               s.is_reit, s.is_bank, s.name,
               p.close
        FROM financials f
        JOIN stocks s ON f.ticker = s.ticker
        LEFT JOIN (
            SELECT ticker, close FROM prices p2
            WHERE date = (SELECT MAX(date) FROM prices WHERE ticker = p2.ticker)
        ) p ON f.ticker = p.ticker
        WHERE f.dps IS NOT NULL AND f.dps > 0
          {where}
        ORDER BY f.ticker, f.year DESC
    """).fetchall()

    # Group by ticker for history-aware checks
    from collections import defaultdict
    by_ticker = defaultdict(list)
    for r in rows:
        by_ticker[r['ticker']].append(dict(r))

    for ticker, history in by_ticker.items():
        # Sort newest-first
        history.sort(key=lambda x: x['year'], reverse=True)

        # ── Check every year individually (not just the most recent) ─────
        for idx, rec in enumerate(history):
            year  = rec['year']
            dps   = rec['dps']
            eps   = rec['eps']
            close = rec['close']
            is_reit = rec['is_reit']

            # ── 1a. Current-year DPS (likely partial / ex-date attributed wrong)
            if year == current_year:
                issues.append({
                    'ticker': ticker,
                    'year':   year,
                    'check':  'Current-year DPS',
                    'severity': 'WARN',
                    'detail': (
                        f"DPS={dps:.4f} stored under {current_year} "
                        f"(ex-div date was in {current_year}). "
                        "These dividends belong to the prior fiscal year."
                    ),
                    'suggested_action': 'Check scraper year attribution; '
                                        'move to prior year or exclude from calendar.',
                })

            # ── 1b. Implausible yield (non-REIT, yield > 15%)
            if close and close > 0 and not is_reit:
                yield_pct = dps / close * 100.0
                if yield_pct > 15.0:
                    # Penny stocks (price < PHP 2) can legitimately show high
                    # yield percentages from small absolute DPS amounts.
                    # Downgrade to WARN so they don't drown out real errors.
                    is_penny = close < 2.0
                    issues.append({
                        'ticker': ticker,
                        'year':   year,
                        'check':  'Implausible yield (>15%)',
                        'severity': 'WARN' if is_penny else 'ERROR',
                        'detail': (
                            f"DPS={dps:.4f}, Price={close:.2f}, "
                            f"Implied yield={yield_pct:.1f}%. "
                            + ("Penny stock -- small absolute DPS can inflate yield pct. "
                               if is_penny else
                               "Likely DPS double-counted or PDF parser error. ")
                        ),
                        'suggested_action': 'Verify dividend history on PSE Edge. '
                                            'Check if scraper summed multiple ex-dates.',
                    })
                elif yield_pct > 10.0 and eps is None:
                    # Can't validate via payout — flag for review
                    prior_list = [h['dps'] for h in history[idx+1:] if h['dps'] and h['year'] < year]
                    jump_factor = (dps / prior_list[0]) if prior_list else None
                    detail = (
                        f"DPS={dps:.4f}, Price={close:.2f}, "
                        f"Implied yield={yield_pct:.1f}%, EPS=NULL (can't validate payout). "
                    )
                    if jump_factor:
                        detail += f"Prior year DPS={prior_list[0]:.4f} ({jump_factor:.1f}x jump)."
                    else:
                        detail += "No prior year DPS to compare against."
                    issues.append({
                        'ticker': ticker,
                        'year':   year,
                        'check':  'High yield + no EPS validation',
                        'severity': 'WARN',
                        'detail': detail,
                        'suggested_action': 'Verify on PSE Edge dividend history. '
                                            'If single data point with no history, treat as unverified.',
                    })

            # ── 1c. Payout ratio > 200% (non-REIT, positive EPS)
            if not is_reit and eps is not None and eps > 0:
                payout = dps / eps * 100.0
                if payout > 200.0:
                    # Holding companies often show high payout vs parent EPS
                    # because they fund dividends from subsidiary earnings not
                    # reflected in parent-only net income. If the yield is low
                    # (<5%), this is almost certainly holding company mechanics
                    # rather than a data error. Downgrade to WARN.
                    holding_co_pattern = (close and close > 0
                                          and (dps / close * 100.0) < 5.0)
                    issues.append({
                        'ticker': ticker,
                        'year':   year,
                        'check':  'Payout ratio >200% (non-REIT)',
                        'severity': 'WARN' if holding_co_pattern else 'ERROR',
                        'detail': (
                            f"DPS={dps:.4f}, EPS={eps:.4f}, "
                            f"Payout={payout:.0f}%. "
                            + ("Yield is low ({:.1f}%) -- likely a holding company "
                               "paying dividends from subsidiary/retained earnings "
                               "not visible in parent EPS. ".format(dps/close*100.0)
                               if holding_co_pattern else
                               "A payout over 200% is impossible "
                               "unless EPS or DPS data is wrong. ")
                        ),
                        'suggested_action': 'Cross-check EPS and DPS on PSE Edge annual report.',
                    })

            # ── 1d. Sudden DPS jump vs prior year (>3x) — only for non-current years
            if year < current_year and idx + 1 < len(history):
                prior_list = [h['dps'] for h in history[idx+1:] if h['dps'] and h['year'] < year]
                if prior_list and dps / prior_list[0] > 3.0:
                    jump = dps / prior_list[0]
                    issues.append({
                        'ticker': ticker,
                        'year':   year,
                        'check':  'DPS jumped >3x vs prior year',
                        'severity': 'WARN',
                        'detail': (
                            f"DPS {prior_list[0]:.4f} -> {dps:.4f} "
                            f"({jump:.1f}x increase). "
                            "Could be a legitimate special dividend or a scraper error."
                        ),
                        'suggested_action': 'Check PSE Edge for special dividend declaration.',
                    })

        # ── 1e. DPS exists but no other financials anywhere (per-ticker check)
        latest = history[0]
        if (latest['eps'] is None and latest['revenue'] is None
                and latest['net_income'] is None):
            any_financials = conn.execute(
                'SELECT 1 FROM financials WHERE ticker=? AND eps IS NOT NULL LIMIT 1',
                (ticker,)
            ).fetchone()
            if not any_financials:
                issues.append({
                    'ticker': ticker,
                    'year':   latest['year'],
                    'check':  'DPS only -- no other financials',
                    'severity': 'INFO',
                    'detail': (
                        f"DPS={latest['dps']:.4f} but revenue, EPS, net_income all NULL. "
                        "This stock has no income statement data in the DB."
                    ),
                    'suggested_action': 'Run scraper for this ticker to pull full financials.',
                })

    # ── 2. EPS / Revenue sanity checks ───────────────────────
    anomaly_rows = conn.execute(f"""
        SELECT f.ticker, f.year, f.eps, f.revenue, f.net_income, f.operating_cf,
               s.name
        FROM financials f
        JOIN stocks s ON f.ticker = s.ticker
        WHERE 1=1 {where}
    """).fetchall()

    for r in anomaly_rows:
        # Negative revenue (impossible unless restatement)
        if r['revenue'] is not None and r['revenue'] < 0:
            issues.append({
                'ticker': r['ticker'],
                'year':   r['year'],
                'check':  'Negative revenue',
                'severity': 'ERROR',
                'detail': f"Revenue={r['revenue']:.2f}M. Revenue cannot be negative.",
                'suggested_action': 'Likely parser error. Re-scrape and verify.',
            })

        # EPS wildly out of range vs revenue (e.g. EPS > revenue/shares suggests unit mismatch)
        if (r['eps'] is not None and r['revenue'] is not None
                and r['revenue'] > 0 and abs(r['eps']) > 500):
            issues.append({
                'ticker': r['ticker'],
                'year':   r['year'],
                'check':  'EPS out of range (>500)',
                'severity': 'WARN',
                'detail': f"EPS={r['eps']:.2f}. Unusually large -- possible unit error (millions vs per-share).",
                'suggested_action': 'Verify EPS figure on PSE Edge annual report.',
            })

        # Net margin > 500% (NI >> Revenue -- likely unit mismatch or huge one-time gain)
        if (r['revenue'] is not None and r['revenue'] > 0
                and r['net_income'] is not None and r['net_income'] > 0
                and r['net_income'] / r['revenue'] > 5.0):
            issues.append({
                'ticker': r['ticker'],
                'year':   r['year'],
                'check':  'Net margin >500%',
                'severity': 'WARN',
                'detail': (
                    f"Revenue={r['revenue']:.2f}M, NI={r['net_income']:.2f}M, "
                    f"Margin={r['net_income']/r['revenue']*100:.0f}%. "
                    "Likely a holding company one-time gain (asset sale, revaluation) "
                    "or unit mismatch (NI in different units than Revenue)."
                ),
                'suggested_action': 'Check PSE Edge annual report for non-recurring items. '
                                    'If holding company, margin distortion is expected.',
            })

    # ── 3. EPS vs NI cross-check using market cap share count ──────
    # When market_cap and close are available, derive actual shares
    # and check if stored EPS is consistent with stored NI.
    # A >100x discrepancy indicates a parser unit error.
    eps_check_rows = conn.execute(f"""
        SELECT f.ticker, f.year, f.net_income, f.eps, p.close, p.market_cap, s.name
        FROM financials f
        JOIN stocks s ON f.ticker = s.ticker
        JOIN (
            SELECT ticker, close, market_cap FROM prices p2
            WHERE date = (SELECT MAX(date) FROM prices WHERE ticker = p2.ticker)
        ) p ON f.ticker = p.ticker
        WHERE f.eps IS NOT NULL AND f.eps > 0
          AND f.net_income IS NOT NULL AND f.net_income > 0
          AND p.market_cap IS NOT NULL AND p.market_cap > 0 AND p.close > 0
          AND f.year >= 2020
          {where}
    """).fetchall()

    for r in eps_check_rows:
        shares = r['market_cap'] / r['close']   # actual shares outstanding
        correct_eps = r['net_income'] * 1_000_000 / shares  # NI in millions -> per share
        stored_eps  = r['eps']
        if correct_eps > 0:
            ratio = stored_eps / correct_eps
            if ratio > 100 or ratio < 0.01:
                issues.append({
                    'ticker': r['ticker'],
                    'year':   r['year'],
                    'check':  'EPS vs NI mismatch (>100x)',
                    'severity': 'ERROR',
                    'detail': (
                        f"Stored EPS={stored_eps:.4f}, NI={r['net_income']:.4f}M, "
                        f"shares={shares/1e6:.0f}M. "
                        f"NI implies EPS~{correct_eps:.4f} ({ratio:.0f}x off). "
                        "Likely a unit error in the EPS parser."
                    ),
                    'suggested_action': 'Null stored EPS and re-scrape from PSE Edge. '
                                        'Check if PDF shows EPS in centavos or thousands.',
                })

    conn.close()
    return issues


def print_report(issues: list[dict], ticker_filter: str = None):
    """Prints a formatted audit report."""
    header = 'PSE Quant - Data Quality Audit'
    if ticker_filter:
        header += f' [{ticker_filter}]'
    print('=' * 70)
    print(f'  {header}')
    print(f'  {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print('=' * 70)

    if not issues:
        print('  No issues found.')
        return

    errors = [i for i in issues if i['severity'] == 'ERROR']
    warns  = [i for i in issues if i['severity'] == 'WARN']
    infos  = [i for i in issues if i['severity'] == 'INFO']

    print(f'  {len(errors)} ERROR(s)  |  {len(warns)} WARNING(s)  |  {len(infos)} INFO(s)')
    print()

    for severity, group in [('ERROR', errors), ('WARN', warns), ('INFO', infos)]:
        if not group:
            continue
        print(f'-- {severity}S {"-"*(60 - len(severity))}')
        for issue in group:
            print(f"\n  [{issue['ticker']}] FY{issue['year']} - {issue['check']}")
            print(f"  Detail: {issue['detail']}")
            print(f"  Action: {issue['suggested_action']}")
        print()


def get_dividend_quality_flags() -> set[tuple]:
    """
    Returns a set of (ticker, year) tuples with suspicious dividend data.
    Used by the calendar query to exclude bad data.

    Excludes any (ticker, year) where:
      - Severity is ERROR and check involves DPS (clear data errors)
      - Any severity with 'yield' in check name (high-yield flags, any level)
      - Any severity with 'Payout' in check name (high-payout flags, any level)

    Conservative by design: a false exclusion is safer than showing bad data.
    """
    issues = run_audit()
    return {
        (i['ticker'], i['year'])
        for i in issues
        if (
            (i['severity'] == 'ERROR' and 'DPS' in i['check'])
            or ('yield' in i['check'])
            or ('Payout' in i['check'])
        )
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='PSE Quant Data Quality Auditor')
    parser.add_argument('--ticker', help='Audit a single ticker (default: all)')
    args = parser.parse_args()

    issues = run_audit(ticker_filter=args.ticker)
    print_report(issues, ticker_filter=args.ticker)
