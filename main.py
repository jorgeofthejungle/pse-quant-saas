# ============================================================
# main.py — PSE Quant SaaS Pipeline Orchestrator (v2)
# PSE Quant SaaS — Phase 13
# ============================================================
# Runs the unified 3-layer sector-aware fundamental pipeline:
#   Load → Validate → Health Filter → Score (3 layers, sector-aware) → MoS → PDF → Discord
#
# Sector-aware scoring: Health + Improvement + Persistence
# Weights vary by portfolio type — see config.py SCORER_WEIGHTS
#
# Data source (auto-selected):
#   1. Real data  — loads from SQLite DB
#   2. Sample data — used if DB is empty (for testing)
#
# Usage:
#   py main.py                  # run unified pipeline
#   py main.py --dry-run        # generate PDF only, no Discord
# ============================================================

import os
import sys
import argparse
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'engine'))
sys.path.insert(0, str(ROOT / 'reports'))
sys.path.insert(0, str(ROOT / 'discord'))
sys.path.insert(0, str(ROOT / 'scraper'))
sys.path.insert(0, str(ROOT / 'db'))

import database as db

from engine.filters_v2    import filter_unified_batch
from engine.scorer_v2     import rank_stocks_v2
from engine.sector_stats  import compute_sector_stats
from validator            import validate_all, print_validation_summary
from pdf_generator        import generate_report
from publisher            import WEBHOOKS, send_report
from mos import (calc_ddm, calc_eps_pe, calc_dcf,
                  calc_hybrid_intrinsic, calc_mos_pct)


# ── MoS weights for unified ranking ───────────────────────────
# Balanced blend: 30% DDM, 35% EPS-PE, 35% DCF
_IV_WEIGHTS = (0.30, 0.35, 0.35)


# ── Data loader ───────────────────────────────────────────────

def load_stocks():
    """Loads stock data from DB; falls back to sample data if empty."""
    try:
        from pse_scraper import load_stocks_from_db
        live = load_stocks_from_db()
        if live:
            print(f"       Using live DB data: {len(live)} stock(s)")
            return live
        print("       DB empty — using sample data")
    except Exception as e:
        print(f"       DB load failed ({e}) — using sample data")
    from scheduler_data import load_sample_stocks
    return load_sample_stocks()


# ── MoS enrichment ────────────────────────────────────────────

def _enrich_mos(stocks: list) -> list:
    """Adds intrinsic_value, mos_price, mos_pct to each stock dict."""
    for stock in stocks:
        try:
            fins   = db.get_financials(stock['ticker'], years=3)
            eps_3y = [f['eps'] for f in fins if f.get('eps') is not None][:3]
            ddm_iv,  _ = calc_ddm(stock.get('dps_last'),
                                   stock.get('dividend_cagr_5y'))
            eps_iv,  _ = calc_eps_pe(eps_3y)
            dcf_iv,  _ = calc_dcf(stock.get('fcf_per_share'),
                                   stock.get('revenue_cagr'))
            is_holding = (stock.get('sector', '') == 'Holding Firms')
            iv, _      = calc_hybrid_intrinsic(ddm_iv, eps_iv, dcf_iv,
                                               weights=_IV_WEIGHTS)
            if is_holding and iv:
                iv = round(iv * 0.80, 2)  # 20% conglomerate discount
        except Exception:
            iv = None
        price = stock.get('current_price')
        stock['intrinsic_value'] = iv
        stock['mos_price']       = round(iv * 0.70, 2) if iv else None
        stock['mos_pct']         = calc_mos_pct(iv, price) if iv and price else None
    return stocks


# ── Sentiment enrichment ──────────────────────────────────────

def _try_enrich_with_sentiment(stocks):
    try:
        from sentiment_engine import enrich_with_sentiment
        enrich_with_sentiment(stocks)
        enriched = sum(1 for s in stocks if s.get('sentiment_data'))
        if enriched:
            print(f"       [sentiment] enriched {enriched} stock(s) with news data")
        else:
            print(f"       [sentiment] no headlines found")
    except Exception as e:
        print(f"       [sentiment] skipped — {e}")


def _send_opportunistic_alerts(ranked_stocks):
    try:
        from publisher import send_opportunistic_alert
        alerts_url = WEBHOOKS.get('alerts', '')
        opp_stocks = [
            s for s in ranked_stocks
            if s.get('sentiment_data', {}) and
               s['sentiment_data'].get('opportunistic_flag')
        ]
        for stock in opp_stocks:
            sd = stock['sentiment_data']
            send_opportunistic_alert(
                stock['ticker'],
                stock.get('name', stock['ticker']),
                sd.get('summary', ''),
                alerts_url,
            )
    except Exception as e:
        print(f"       [sentiment] opportunistic alerts failed — {e}")


# ── Main pipeline ─────────────────────────────────────────────

def run_pipeline(dry_run: bool = False) -> bool:
    """
    Runs the full unified v2 pipeline.
    Returns True if completed successfully.
    """
    print(f"\n{'='*55}")
    print(f"  PSE QUANT SAAS — Unified Rankings")
    print(f"  {datetime.now().strftime('%Y-%m-%d  %H:%M')}")
    print(f"{'='*55}")

    # ── Step 1: Load & validate ───────────────────────────────
    print("\n[1/5]  Loading stock data...")
    all_stocks = load_stocks()
    print(f"       {len(all_stocks)} stocks loaded")

    all_stocks, val_results = validate_all(all_stocks)
    blocked = sum(1 for r in val_results if not r['valid'])
    warned  = sum(1 for r in val_results if r['warnings'])
    if blocked:
        print(f"       Validation blocked {blocked} stock(s)")
    if warned:
        for r in val_results:
            for w in r['warnings']:
                print(f"       WARN  {w}")
    print(f"       {len(all_stocks)} stock(s) passed validation")

    if not all_stocks:
        print("  No stocks passed validation.")
        return False

    # ── Step 2: Compute sector medians ────────────────────────
    print("\n[2/5]  Computing sector statistics...")
    sector_stats = compute_sector_stats(all_stocks)
    print(f"       Sector medians computed for {len(sector_stats)} sector(s)")

    # ── Step 3: Health filter + score ─────────────────────────
    print("\n[3/5]  Filtering and scoring...")
    eligible, rejected = filter_unified_batch(all_stocks)
    print(f"       Eligible : {len(eligible)} stock(s)")
    print(f"       Rejected : {len(rejected)} stock(s)")
    for r in rejected:
        print(f"         SKIP  {r['reason']}")

    if not eligible:
        print("  No stocks passed health filters.")
        return False

    # Build financials history map for ROE delta (Layer 2)
    fins_map = {}
    for stock in eligible:
        try:
            fins_map[stock['ticker']] = db.get_financials(stock['ticker'], years=10)
        except Exception:
            fins_map[stock['ticker']] = []

    # Score each portfolio type separately with portfolio-specific weights
    from db.db_scores import save_scores_v2
    portfolio_types  = ['dividend', 'value']
    ranked_sections  = {}
    run_date         = datetime.now().strftime('%Y-%m-%d')

    for pt in portfolio_types:
        ranked_pt = rank_stocks_v2(eligible, sector_stats=sector_stats,
                                   financials_map=fins_map,
                                   portfolio_type=pt)
        save_scores_v2(run_date, ranked_pt, portfolio_type=pt)
        ranked_sections[pt] = ranked_pt
        print(f"       {pt}: {len(ranked_pt)} stock(s) scored")

    # Use dividend ranking as the primary list for sentiment + alerts
    ranked = ranked_sections.get('dividend', [])
    print(f"\n  Top 10 (Dividend weights):")
    for s in ranked[:10]:
        cat = s.get('category', '')
        print(f"    #{s['rank']:2}  {s['ticker']:6}  {s['score']:.1f}  [{cat}]")

    # ── Step 3b: MoS enrichment (all sections) ───────────────
    for pt in portfolio_types:
        ranked_sections[pt] = _enrich_mos(ranked_sections[pt])

    # ── Step 3c: Sentiment enrichment (top 10 from dividend) ──
    _try_enrich_with_sentiment(ranked_sections['dividend'][:10])

    # ── Step 4: Generate unified PDF ─────────────────────────
    print(f"\n[4/5]  Generating unified PDF report...")
    from config import REPORTS_DIR
    _desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
    _out_dir = os.environ.get('PDF_OUTPUT_DIR',
                              _desktop if os.path.isdir(_desktop) else REPORTS_DIR)
    os.makedirs(_out_dir, exist_ok=True)
    filename = f"StockPilot_PH_Rankings_{run_date}.pdf"
    pdf_path = os.path.join(_out_dir, filename)

    generate_report(
        ranked_sections        = ranked_sections,
        output_path            = pdf_path,
        total_stocks_screened  = len(all_stocks),
    )
    print(f"       Saved: {pdf_path}")

    # ── Step 5: Send to Discord (#pse-value webhook) ──────────
    print(f"\n[5/5]  Discord delivery...")
    if dry_run:
        print("  [DRY RUN] Skipping Discord delivery.")
        return True

    webhook_url = WEBHOOKS.get('rankings', '')
    if not webhook_url:
        print("  No Discord webhook set. Add DISCORD_WEBHOOK_RANKINGS to .env")
        return True

    # Send using the dividend ranked list for the embed summary
    success = send_report(
        webhook_url    = webhook_url,
        pdf_path       = pdf_path,
        portfolio_type = 'unified',
        ranked_stocks  = ranked_sections['dividend'],
    )
    if success:
        print("  Delivered to Discord.")
    else:
        print(f"  Discord delivery failed. PDF saved at: {pdf_path}")

    _send_opportunistic_alerts(ranked_sections['dividend'])
    return True


# ── Entry point ───────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='PSE Quant SaaS — Unified 3-Layer Rankings',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'Examples:\n'
            '  py main.py            # run unified pipeline\n'
            '  py main.py --dry-run  # generate PDF, no Discord\n'
        )
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Generate PDF but do not send to Discord',
    )
    args = parser.parse_args()

    db.init_db()
    run_pipeline(dry_run=args.dry_run)

    print(f"\n{'='*55}")
    print(f"  Done.  {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*55}\n")


if __name__ == '__main__':
    main()
