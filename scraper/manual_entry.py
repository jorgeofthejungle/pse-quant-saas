# ============================================================
# manual_entry.py — Manual Financial Data Entry
# PSE Quant SaaS — Phase 3
# ============================================================
# Fallback for companies whose data cannot be scraped
# from PSE Edge (e.g. companies that file in non-standard
# formats or whose PDFs are unstructured).
#
# Usage:
#   py scraper/manual_entry.py --ticker DMC --year 2022
#       Interactive prompt for each financial field.
#       Press Enter to skip a field (leaves existing DB value unchanged).
#
#   py scraper/manual_entry.py --csv path/to/data.csv
#       Bulk import from CSV file.
#
# CSV format (header row required):
#   ticker,year,revenue,net_income,equity,total_debt,
#   cash,operating_cf,capex,ebitda,eps,dps
#
#   All monetary values in millions PHP.
#   eps and dps in PHP per share.
#   Leave cells blank to skip (existing DB value preserved).
# ============================================================

import sys
import os
import csv
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT))

import database as db


# ── Field definitions ─────────────────────────────────────────

FIELDS = [
    ('revenue',     'Revenue (total, M PHP)'),
    ('net_income',  'Net Income after tax (M PHP)'),
    ('equity',      'Stockholders Equity (M PHP)'),
    ('total_debt',  'Total Liabilities or Debt (M PHP)'),
    ('cash',        'Cash and Cash Equivalents (M PHP)'),
    ('operating_cf','Operating Cash Flow (M PHP)'),
    ('capex',       'Capital Expenditures (M PHP)'),
    ('ebitda',      'EBITDA (M PHP)'),
    ('eps',         'Earnings Per Share - basic (PHP/share)'),
    ('dps',         'Dividends Per Share (PHP/share)'),
]


# ── Interactive entry ─────────────────────────────────────────

def enter_financials(ticker: str, year: int) -> bool:
    """
    Interactive prompts for each financial field.
    Press Enter to skip a field (existing DB value is preserved).
    Returns True if at least one field was entered.
    """
    ticker = ticker.upper()
    print(f"\nManual entry: {ticker} FY{year}")
    print("Press Enter to skip a field (keeps existing DB value).")
    print("-" * 50)

    # Show existing values if any
    existing = {}
    rows = db.get_financials(ticker, years=10)
    for r in rows:
        if r['year'] == year:
            existing = r
            break

    if existing:
        print(f"Existing values in DB for {ticker} {year}:")
        for key, label in FIELDS:
            val = existing.get(key)
            if val is not None:
                print(f"  {label}: {val}")
        print()

    values = {}
    for key, label in FIELDS:
        existing_val = existing.get(key)
        prompt = f"  {label}"
        if existing_val is not None:
            prompt += f" [current: {existing_val}]"
        prompt += ": "

        raw = input(prompt).strip()
        if not raw:
            continue

        try:
            values[key] = float(raw.replace(',', ''))
        except ValueError:
            print(f"    Invalid number: {raw!r} — skipped")

    if not values:
        print("No values entered — nothing saved.")
        return False

    db.upsert_financials(ticker=ticker, year=year, **values)
    print(f"\nSaved {len(values)} field(s) for {ticker} {year}:")
    for k, v in values.items():
        print(f"  {k} = {v}")
    return True


# ── CSV import ────────────────────────────────────────────────

MONETARY_FIELDS = {'revenue', 'net_income', 'equity', 'total_debt',
                   'cash', 'operating_cf', 'capex', 'ebitda'}
PER_SHARE_FIELDS = {'eps', 'dps'}
ALL_FIELDS       = MONETARY_FIELDS | PER_SHARE_FIELDS


def import_csv(csv_path: str) -> int:
    """
    Bulk import from a CSV file.
    CSV must have a header row. Blank cells are skipped.

    Required columns: ticker, year
    Optional columns: revenue, net_income, equity, total_debt,
                      cash, operating_cf, capex, ebitda, eps, dps

    Returns count of rows successfully saved.
    """
    path = Path(csv_path)
    if not path.exists():
        print(f"Error: file not found: {csv_path}")
        return 0

    saved = 0
    errors = 0

    with open(path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        if 'ticker' not in reader.fieldnames or 'year' not in reader.fieldnames:
            print("Error: CSV must have 'ticker' and 'year' columns.")
            return 0

        for i, row in enumerate(reader, 1):
            ticker = row.get('ticker', '').strip().upper()
            year_raw = row.get('year', '').strip()

            if not ticker or not year_raw:
                print(f"  Row {i}: missing ticker or year — skipped")
                errors += 1
                continue

            try:
                year = int(year_raw)
            except ValueError:
                print(f"  Row {i}: invalid year '{year_raw}' — skipped")
                errors += 1
                continue

            values = {}
            for field in ALL_FIELDS:
                raw = (row.get(field) or '').strip()
                if not raw:
                    continue
                try:
                    values[field] = float(raw.replace(',', ''))
                except ValueError:
                    print(f"  Row {i} {ticker} {year} '{field}': invalid value '{raw}' — skipped")

            if not values:
                print(f"  Row {i} {ticker} {year}: no numeric values — skipped")
                continue

            # Ensure ticker exists in stocks table (create placeholder if needed)
            existing_tickers = db.get_all_tickers()
            if ticker not in existing_tickers:
                db.upsert_stock(ticker=ticker, name=ticker, sector='Unknown')

            db.upsert_financials(ticker=ticker, year=year, **values)
            saved += 1
            print(f"  Row {i}: saved {ticker} {year} ({len(values)} fields)")

    print(f"\nImport complete: {saved} rows saved, {errors} skipped.")
    return saved


# ── View existing data ────────────────────────────────────────

def show_financials(ticker: str) -> None:
    """Print all stored financial data for a ticker."""
    ticker = ticker.upper()
    rows = db.get_financials(ticker, years=10)
    if not rows:
        print(f"No financials in DB for {ticker}.")
        return

    print(f"\n{ticker} - financials in DB:")
    print(f"  {'Year':<6} {'Revenue':>12} {'NetIncome':>12} {'Equity':>12} "
          f"{'TotDebt':>12} {'EPS':>6} {'DPS':>6}")
    print("  " + "-" * 70)
    for r in rows:
        def _fmt(v):
            return f"{v:>12,.1f}" if v is not None else f"{'N/A':>12}"
        def _fmt_ps(v):
            return f"{v:>6.2f}" if v is not None else f"{'N/A':>6}"
        print(f"  {r['year']:<6} {_fmt(r['revenue'])} {_fmt(r['net_income'])} "
              f"{_fmt(r['equity'])} {_fmt(r['total_debt'])} "
              f"{_fmt_ps(r['eps'])} {_fmt_ps(r['dps'])}")


# ── CSV template ──────────────────────────────────────────────

def write_csv_template(output_path: str) -> None:
    """Write a blank CSV template to the given path."""
    columns = ['ticker', 'year'] + [f for f, _ in FIELDS]
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        # Example row
        writer.writerow(['DMC', '2022', '', '', '', '', '', '', '', '', '', ''])
    print(f"Template written to: {output_path}")


# ── CLI ───────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='PSE Quant - Manual Financial Data Entry',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  py scraper/manual_entry.py --ticker DMC --year 2022
      Interactive entry for DMC FY2022

  py scraper/manual_entry.py --csv data/financials.csv
      Bulk import from CSV file

  py scraper/manual_entry.py --view DMC
      Show all stored financials for DMC

  py scraper/manual_entry.py --template data/template.csv
      Write a blank CSV template
        """
    )

    parser.add_argument('--ticker', help='Ticker symbol (e.g. DMC)')
    parser.add_argument('--year',   type=int, help='Fiscal year (e.g. 2022)')
    parser.add_argument('--csv',    help='Path to CSV file for bulk import')
    parser.add_argument('--view',   help='Show stored financials for a ticker')
    parser.add_argument('--template', help='Write blank CSV template to this path')
    args = parser.parse_args()

    db.init_db()

    if args.template:
        write_csv_template(args.template)

    elif args.csv:
        import_csv(args.csv)

    elif args.view:
        show_financials(args.view)

    elif args.ticker and args.year:
        enter_financials(args.ticker, args.year)

    else:
        parser.print_help()
