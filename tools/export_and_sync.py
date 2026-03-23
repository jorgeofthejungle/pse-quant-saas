"""
tools/export_and_sync.py
------------------------
Exports stocks, financials, and prices from the local DB and POSTs them
to the Railway import endpoint in batches.

Usage:
    py tools/export_and_sync.py --url https://your-railway-url.railway.app
"""
import sys
import json
import time
import sqlite3
import argparse
import urllib.request
import urllib.error
from pathlib import Path

LOCAL_DB = Path(r'C:\Users\Josh\AppData\Local\pse_quant\pse_quant.db')
BATCH    = 200   # rows per POST (smaller to avoid timeouts)
RETRIES  = 3
RETRY_DELAY = 5  # seconds


def fetch_table(conn, sql, params=()):
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def post_batch(url, table, rows):
    payload = json.dumps({'table': table, 'rows': rows}).encode()
    req = urllib.request.Request(
        url,
        data    = payload,
        headers = {'Content-Type': 'application/json'},
        method  = 'POST',
    )
    for attempt in range(1, RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:200]
            if 'locked' in body and attempt < RETRIES:
                print(f'    DB locked — retrying in {RETRY_DELAY}s ({attempt}/{RETRIES})')
                time.sleep(RETRY_DELAY)
                continue
            print(f'  HTTP {e.code}: {body}')
            return None
        except Exception as e:
            if attempt < RETRIES:
                print(f'    Error: {e} — retrying in {RETRY_DELAY}s ({attempt}/{RETRIES})')
                time.sleep(RETRY_DELAY)
                continue
            print(f'  Error: {e}')
            return None
    return None


def sync_table(conn, import_url, table, sql):
    rows = fetch_table(conn, sql)
    print(f'\n{table}: {len(rows)} rows to sync')
    inserted = 0
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i + BATCH]
        result = post_batch(import_url, table, batch)
        if result:
            inserted += result.get('inserted', 0)
            print(f'  Batch {i // BATCH + 1}: {result}')
        else:
            print(f'  Batch {i // BATCH + 1}: FAILED')
    print(f'  Done — {inserted} rows inserted')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True,
                        help='Railway base URL e.g. https://xyz.railway.app')
    args = parser.parse_args()

    import_url = args.url.rstrip('/') + '/pipeline/import-db'
    print(f'Target: {import_url}')
    print(f'Local DB: {LOCAL_DB}')

    if not LOCAL_DB.exists():
        print('ERROR: Local DB not found')
        sys.exit(1)

    conn = sqlite3.connect(LOCAL_DB)

    # 1. Sync stocks first (required for foreign key constraints)
    sync_table(conn, import_url, 'stocks',
               'SELECT ticker, name, sector, is_reit, is_bank, status, '
               'cmpy_id, fiscal_year_end_month FROM stocks')

    # 2. Sync financials
    sync_table(conn, import_url, 'financials',
               'SELECT ticker, year, revenue, net_income, equity, total_debt, '
               'cash, operating_cf, capex, ebitda, eps, dps FROM financials')

    # 3. Sync prices (last 400 days)
    sync_table(conn, import_url, 'prices',
               "SELECT ticker, date, close, market_cap FROM prices "
               "WHERE date >= date('now', '-400 days')")

    conn.close()
    print('\nSync complete. Run scoring on Railway to update rankings.')


if __name__ == '__main__':
    main()
