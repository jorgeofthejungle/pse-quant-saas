# ============================================================
# conglomerate_autofill.py — Auto-populate Segment Data from DB
# PSE Quant SaaS
# ============================================================
# For each listed subsidiary in CONGLOMERATE_MAP, pulls the
# latest financials from the DB and upserts them as segment
# data for the parent conglomerate.
#
# Unlisted subsidiaries are left untouched (manual entries).
#
# Called by scheduler_jobs.run_weekly_scrape() after scraping.
# Can also be called standalone: py engine/conglomerate_autofill.py
# ============================================================

from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT / 'engine'))
sys.path.insert(0, str(ROOT))

from engine.conglomerate_map import CONGLOMERATE_MAP


def autofill_segments_from_db(verbose: bool = False) -> dict[str, int]:
    """
    Reads each listed subsidiary's latest financials from the DB
    and upserts them as segment rows for the parent conglomerate.

    Skips unlisted subsidiaries (ticker=None) — those use manual entries.
    Skips if no financials found in DB for the child ticker.

    Returns {parent_ticker: count_of_segments_updated}
    """
    from db.db_connection import get_connection
    from db.db_conglomerates import upsert_segment

    conn   = get_connection()
    totals: dict[str, int] = {}

    for parent, segments in CONGLOMERATE_MAP.items():
        updated = 0

        for seg in segments:
            child_ticker = seg.get('ticker')
            if not child_ticker:
                continue  # unlisted — skip, keep manual entry

            # Get latest year WITH actual financial data (skip NULL skeleton rows)
            row = conn.execute("""
                SELECT year, revenue, net_income, equity
                FROM financials
                WHERE ticker = ?
                  AND (revenue IS NOT NULL OR net_income IS NOT NULL)
                ORDER BY year DESC
                LIMIT 1
            """, (child_ticker,)).fetchone()

            if not row:
                if verbose:
                    print(f'  [{parent}] {seg["name"]} — no DB data for {child_ticker}, skipped')
                continue

            year       = row['year']
            revenue    = row['revenue']
            net_income = row['net_income']
            equity     = row['equity']

            upsert_segment(
                parent_ticker  = parent,
                segment_name   = seg['name'],
                year           = year,
                revenue        = revenue,
                net_income     = net_income,
                equity         = equity,
                segment_ticker = child_ticker,
                notes          = seg.get('notes', f'Auto-filled from {child_ticker} DB financials'),
            )
            updated += 1

            if verbose:
                ni_str = f'{net_income:,.0f}M' if net_income is not None else 'N/A'
                print(f'  [{parent}] {seg["name"]} ({child_ticker}) — {year} NI: {ni_str}')

        totals[parent] = updated

    conn.close()
    return totals


def run_autofill(verbose: bool = True) -> None:
    """Entry point — prints summary of what was updated."""
    print('Auto-filling conglomerate segments from DB...')
    results = autofill_segments_from_db(verbose=verbose)
    total   = sum(results.values())
    print(f'\nDone. {total} listed-subsidiary segments updated across {len(results)} conglomerates.')
    for parent, count in results.items():
        print(f'  {parent}: {count} segments updated')


if __name__ == '__main__':
    run_autofill(verbose=True)
