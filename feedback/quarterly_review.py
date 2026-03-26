# feedback/quarterly_review.py — Quarterly Diagnostic + Auto-Correction (Tier 2)
# Diagnoses structural weaknesses and applies guarded auto-corrections to
# sector layer weights. Pure deterministic math — no AI calls, no scipy.

import json
import statistics
from datetime import date, datetime, timezone
from db.db_connection import get_connection
from config import (
    BLIND_SPOT_SCORE_THRESHOLD, BLIND_SPOT_RETURN_THRESHOLD,
    SECTOR_BIAS_Z_THRESHOLD, SECTOR_MIN_BANKS, SECTOR_MIN_REITS, SECTOR_MIN_DEFAULT,
    SCORER_WEIGHTS,
)
from engine.sector_groups import get_scoring_group

PORTFOLIO_TYPES = ['dividend', 'value']
QUARTER_MONTHS  = {'Q1': ['01','02','03'], 'Q2': ['04','05','06'],
                   'Q3': ['07','08','09'], 'Q4': ['10','11','12']}
SECTOR_MINIMUMS = {'bank': SECTOR_MIN_BANKS, 'reit': SECTOR_MIN_REITS}
MAX_QTR_ADJ     = 0.03   # 3% max per-quarter adjustment
MAX_CUMULATIVE  = 0.08   # 8% cumulative cap
LAYER_FLOOR     = 0.10   # no layer below 10%


# ── Helpers ───────────────────────────────────────────────────────────────────

def _prev_quarter() -> str:
    today = date.today()
    y, m = today.year, today.month
    if m <= 3:
        return f"{y-1}-Q4"
    elif m <= 6:
        return f"{y}-Q1"
    elif m <= 9:
        return f"{y}-Q2"
    return f"{y}-Q3"


def _quarter_months(quarter: str) -> list[str]:
    year, q = quarter.split('-')
    return [f"{year}-{mo}" for mo in QUARTER_MONTHS.get(q, [])]


def _zscore_list(values: list[float]) -> list[float]:
    if len(values) <= 1:
        return [0.0] * len(values)
    mean  = statistics.mean(values)
    stdev = statistics.pstdev(values)
    if stdev == 0:
        return [0.0] * len(values)
    return [(v - mean) / stdev for v in values]


def _safe_mean(vals: list) -> float | None:
    cleaned = [v for v in vals if v is not None]
    return statistics.mean(cleaned) if cleaned else None


def _get_setting(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row['value'] if row else None


def _set_setting(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
        (key, value, datetime.utcnow().isoformat()),
    )


def _log_diag(conn, quarter, portfolio_type, sector, metric_name, metric_value,
              z_score, met_threshold, bias_direction, bias_magnitude, stock_count, notes):
    try:
        conn.execute(
            "INSERT INTO feedback_diagnostic_log "
            "(quarter, portfolio_type, sector, metric_name, metric_value, z_score, "
            " met_threshold, bias_direction, bias_magnitude, stock_count, notes, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (quarter, portfolio_type, sector, metric_name, metric_value, z_score,
             1 if met_threshold else 0, bias_direction, bias_magnitude,
             stock_count, notes, datetime.utcnow().isoformat()),
        )
    except Exception as exc:
        print(f"[quarterly] WARNING: diag log failed: {exc}")


def _get_stock_info(conn, ticker: str) -> dict:
    row = conn.execute(
        "SELECT ticker, sector, is_bank, is_reit FROM stocks WHERE ticker = ?", (ticker,)
    ).fetchone()
    return dict(row) if row else {'ticker': ticker, 'sector': None, 'is_bank': 0, 'is_reit': 0}


def _notify(msg: str) -> None:
    try:
        from feedback import discord_feedback  # type: ignore
        discord_feedback.send_admin_dm(msg)
    except Exception:
        print(f"[quarterly] {msg}")


# ── Public entry points ───────────────────────────────────────────────────────

def run_quarterly_review(quarter: str | None = None) -> dict | None:
    """Run the 11-step quarterly diagnostic for all portfolio types."""
    if quarter is None:
        quarter = _prev_quarter()
    print(f"[quarterly] Running review for quarter={quarter}")
    conn = None
    try:
        conn = get_connection()
    except Exception as exc:
        print(f"[quarterly] ERROR: cannot open DB: {exc}")
        return None
    results = {}
    try:
        for pt in PORTFOLIO_TYPES:
            r = _run_for_portfolio(conn, quarter, pt)
            if r is not None:
                results[pt] = r
    except Exception as exc:
        print(f"[quarterly] ERROR: {exc}")
    finally:
        if conn is not None:
            conn.close()
    return results if results else None


def get_quarterly_review(quarter: str, portfolio_type: str) -> dict | None:
    """Return stored feedback_quarterly row as dict, or None."""
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM feedback_quarterly WHERE quarter = ? AND portfolio_type = ?",
            (quarter, portfolio_type),
        ).fetchone()
        return dict(row) if row else None
    except Exception as exc:
        print(f"[quarterly] ERROR: get_quarterly_review: {exc}")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ── Core algorithm ────────────────────────────────────────────────────────────

def _run_for_portfolio(conn, quarter: str, portfolio_type: str) -> dict | None:

    # ── Step 1: Aggregate Monthly Data ────────────────────────────────────────
    months = _quarter_months(quarter)
    ph = ','.join('?' * len(months))
    monthly_rows = [
        dict(r) for r in conn.execute(
            f"SELECT * FROM feedback_monthly "
            f"WHERE portfolio_type=? AND month IN ({ph}) ORDER BY month ASC",
            [portfolio_type] + months,
        ).fetchall()
    ]
    if len(monthly_rows) < 3:
        print(f"[quarterly] {portfolio_type}/{quarter}: {len(monthly_rows)} scorecards — need 3.")
        return None

    avg_monthly_top10_return = _safe_mean([r.get('top10_avg_return') for r in monthly_rows])
    avg_monthly_hit_rate     = _safe_mean([r.get('hit_rate_positive') for r in monthly_rows])
    avg_monthly_mos_accuracy = _safe_mean([r.get('mos_direction_accuracy') for r in monthly_rows])
    avg_spearman             = _safe_mean([r.get('spearman_correlation') for r in monthly_rows])

    # ── Step 2: Evaluation Window + Quarterly Returns ─────────────────────────
    year, q = quarter.split('-')
    q_months = QUARTER_MONTHS.get(q, [])
    first_start = f"{year}-{q_months[0]}-01" if q_months else None
    last_m = int(q_months[-1]) if q_months else 12
    next_start = f"{int(year)+1}-01-01" if last_m == 12 else f"{year}-{str(last_m+1).zfill(2)}-01"

    if not first_start:
        return None

    all_snaps = [
        dict(r) for r in conn.execute(
            "SELECT * FROM feedback_snapshots "
            "WHERE portfolio_type=? AND snapshot_date>=? AND snapshot_date<? "
            "ORDER BY snapshot_date ASC",
            (portfolio_type, first_start, next_start),
        ).fetchall()
    ]
    if not all_snaps:
        print(f"[quarterly] {portfolio_type}/{quarter}: no snapshots found.")
        return None

    all_dates = sorted(set(s['snapshot_date'] for s in all_snaps))
    t0, t1 = min(all_dates), max(all_dates)
    snaps_t0 = {s['ticker']: s for s in all_snaps if s['snapshot_date'] == t0}
    snaps_t1 = {s['ticker']: s for s in all_snaps if s['snapshot_date'] == t1}

    quarterly_returns: dict[str, float] = {}
    for ticker in snaps_t0:
        if ticker not in snaps_t1:
            continue
        p0 = snaps_t0[ticker].get('price_at_snapshot')
        p1 = snaps_t1[ticker].get('price_at_snapshot')
        if p0 and p1 and float(p0) != 0:
            quarterly_returns[ticker] = (float(p1) - float(p0)) / float(p0)

    total_stocks_evaluated = len(quarterly_returns)

    # ── Step 10 (early): Confidence Level ─────────────────────────────────────
    if total_stocks_evaluated >= 50:
        confidence_level = 'high'
    elif total_stocks_evaluated >= 30:
        confidence_level = 'medium'
    else:
        confidence_level = 'low'

    # ── Step 3: Blind Spot Detection ──────────────────────────────────────────
    blind_spots = [
        t for t, qr in quarterly_returns.items()
        if snaps_t0.get(t) and snaps_t0[t].get('score') is not None
        and float(snaps_t0[t]['score']) > BLIND_SPOT_SCORE_THRESHOLD
        and qr < -BLIND_SPOT_RETURN_THRESHOLD
    ]

    # ── Step 4: Sector Bias Calculation ───────────────────────────────────────
    sector_data: dict[str, list[dict]] = {}
    for ticker, qr in quarterly_returns.items():
        score_t0 = snaps_t0[ticker].get('score')
        if score_t0 is None:
            continue
        info  = _get_stock_info(conn, ticker)
        group = get_scoring_group(info)
        sector_data.setdefault(group, []).append({'ticker': ticker, 'score': float(score_t0), 'return': qr})

    sectors_skipped: list[str] = []
    qualifying: dict[str, dict] = {}
    for group, stocks in sector_data.items():
        min_req = SECTOR_MINIMUMS.get(group, SECTOR_MIN_DEFAULT)
        if len(stocks) < min_req:
            sectors_skipped.append(group)
        else:
            qualifying[group] = {
                'avg_score':   statistics.mean(s['score'] for s in stocks),
                'avg_return':  statistics.mean(s['return'] for s in stocks),
                'stock_count': len(stocks),
            }

    groups_list    = list(qualifying.keys())
    score_z_map    = dict(zip(groups_list, _zscore_list([qualifying[g]['avg_score']  for g in groups_list])))
    return_z_map   = dict(zip(groups_list, _zscore_list([qualifying[g]['avg_return'] for g in groups_list])))

    sectors_flagged: list[str] = []
    sector_bias_raw: dict[str, dict] = {}
    for group in groups_list:
        bias    = score_z_map[group] - return_z_map[group]
        flagged = abs(bias) > SECTOR_BIAS_Z_THRESHOLD
        sector_bias_raw[group] = {
            'avg_score': qualifying[group]['avg_score'],
            'avg_return': qualifying[group]['avg_return'],
            'bias': bias, 'flagged': flagged,
        }
        if flagged:
            sectors_flagged.append(group)
        _log_diag(conn, quarter, portfolio_type, group, 'sector_bias', bias, bias,
                  flagged, 'over' if bias > 0 else 'under', abs(bias),
                  qualifying[group]['stock_count'], None)

    # ── Step 5: Score Band Analysis ───────────────────────────────────────────
    bands = [('80-100', 80, 101), ('65-79', 65, 80), ('50-64', 50, 65), ('0-49', 0, 50)]
    score_band_data: dict[str, dict] = {}
    for label, lo, hi in bands:
        band_rets = [
            qr for t, qr in quarterly_returns.items()
            if snaps_t0.get(t) and snaps_t0[t].get('score') is not None
            and lo <= float(snaps_t0[t]['score']) < hi
        ]
        score_band_data[label] = {
            'avg_return': statistics.mean(band_rets) if band_rets else None,
            'stock_count': len(band_rets),
        }

    band_inversion_flag = False
    for i, (lbl, _, _) in enumerate(bands[:-1]):
        hi_ret = score_band_data[bands[i][0]]['avg_return']
        lo_ret = score_band_data[bands[i+1][0]]['avg_return']
        if hi_ret is not None and lo_ret is not None and hi_ret < lo_ret:
            band_inversion_flag = True
            break

    # ── Step 6: Persistence Tracking ──────────────────────────────────────────
    prev_row = conn.execute(
        "SELECT consecutive_bias_quarters FROM feedback_quarterly "
        "WHERE portfolio_type=? AND quarter<? ORDER BY quarter DESC LIMIT 1",
        (portfolio_type, quarter),
    ).fetchone()
    prev_cbq: dict[str, int] = {}
    if prev_row and prev_row['consecutive_bias_quarters']:
        try:
            prev_cbq = json.loads(prev_row['consecutive_bias_quarters'])
        except (json.JSONDecodeError, TypeError):
            prev_cbq = {}

    consecutive_bias_quarters: dict[str, int] = {
        g: (prev_cbq.get(g, 0) + 1 if sector_bias_raw.get(g, {}).get('flagged') else 0)
        for g in groups_list
    }

    # ── Step 7: Score Instability Review ──────────────────────────────────────
    inst_rows = conn.execute(
        f"SELECT ticker, score_change_flag FROM feedback_stock_returns "
        f"WHERE portfolio_type=? AND month IN ({ph})",
        [portfolio_type] + months,
    ).fetchall()
    flag_counts: dict[str, int] = {}
    for row in inst_rows:
        if row['score_change_flag'] == 1:
            flag_counts[row['ticker']] = flag_counts.get(row['ticker'], 0) + 1
    recurring_unstable_count = sum(1 for c in flag_counts.values() if c >= 2)

    # ── Steps 8 & 9: Gatekeeper + Auto-Correction ─────────────────────────────
    corrections_applied: list[dict] = []
    corrections_blocked: list[dict] = []
    overall_avg_ret = _safe_mean([qualifying[g]['avg_return'] for g in qualifying])

    for group in sectors_flagged:
        bias      = sector_bias_raw[group]['bias']
        bias_mag  = abs(bias)
        stk_count = qualifying[group]['stock_count']
        min_req   = SECTOR_MINIMUMS.get(group, SECTOR_MIN_DEFAULT)
        consec    = consecutive_bias_quarters.get(group, 0)

        fails: list[str] = []
        if consec < 2:
            fails.append(f"consecutive_bias_quarters={consec} (need >=2)")
        if bias_mag <= SECTOR_BIAS_Z_THRESHOLD:
            fails.append(f"abs(bias)={bias_mag:.3f} <= threshold {SECTOR_BIAS_Z_THRESHOLD}")
        if stk_count < min_req:
            fails.append(f"stock_count={stk_count} < minimum {min_req}")
        if confidence_level == 'low':
            fails.append(f"confidence_level='low' (need medium or high)")

        sector_blind = [t for t in blind_spots if get_scoring_group(_get_stock_info(conn, t)) == group]
        sect_underperf = overall_avg_ret is not None and qualifying[group]['avg_return'] < overall_avg_ret
        if not (band_inversion_flag or sector_blind or sect_underperf):
            fails.append("no structural confirmation (band inversion / blind spots / underperformance)")

        if fails:
            corrections_blocked.append({'sector': group, 'reason': fails, 'bias': bias, 'consecutive_quarters': consec})
            continue

        # Apply correction
        layer = 'health'
        ck    = f"feedback_correction_{group}_{layer}"

        # Read existing correction (single JSON blob)
        existing_row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (ck,)
        ).fetchone()
        if existing_row:
            try:
                existing = json.loads(existing_row[0])
            except Exception:
                existing = {}
        else:
            existing = {}

        cum_exist = existing.get('cumulative', 0.0) or 0.0
        version   = existing.get('version', 0) or 0

        direction  = -1.0 if bias > 0 else 1.0
        cw         = 1.0 if (avg_spearman is not None and avg_spearman > 0 and confidence_level != 'low') else 0.5
        final_adjustment = min(bias_mag * 0.3 * cw, MAX_QTR_ADJ) * direction

        new_cum = cum_exist + final_adjustment
        if abs(new_cum) > MAX_CUMULATIVE:
            corrections_blocked.append({'sector': group, 'reason': [f"cumulative cap: {new_cum:.4f} > {MAX_CUMULATIVE}"],
                                         'bias': bias, 'consecutive_quarters': consec})
            continue

        base_wts  = SCORER_WEIGHTS.get(portfolio_type) or SCORER_WEIGHTS.get('unified', {})
        projected = base_wts.get(layer, 0.30) + cum_exist + final_adjustment
        if projected < LAYER_FLOOR:
            corrections_blocked.append({'sector': group, 'reason': [f"layer floor: {projected:.4f} < {LAYER_FLOOR}"],
                                         'bias': bias, 'consecutive_quarters': consec})
            continue

        # Write single JSON blob
        _now = datetime.now(timezone.utc).isoformat()
        correction_blob = json.dumps({
            'adjustment':     round(final_adjustment, 6),
            'quarter':        quarter,
            'cumulative':     round(cum_exist + final_adjustment, 6),
            'version':        version + 1,
            'previous_value': round(cum_exist, 6),
            'status':         'active',
            'applied_at':     _now,
        })
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (ck, correction_blob, _now)
        )
        corrections_applied.append({
            'sector': group, 'layer': layer, 'adjustment': final_adjustment,
            'new_correction': round(cum_exist + final_adjustment, 6), 'new_cumulative': round(new_cum, 6),
            'bias': bias, 'consecutive_quarters': consec, 'status': 'active',
        })
        print(f"[quarterly] Correction: {group}/{layer} adj={final_adjustment:+.4f} cumulative={new_cum:.4f}")

    # ── Step 11: Store & Notify ────────────────────────────────────────────────
    review = {
        'quarter': quarter, 'portfolio_type': portfolio_type,
        'evaluation_window_start': t0, 'evaluation_window_end': t1,
        'avg_monthly_top10_return': avg_monthly_top10_return,
        'avg_monthly_hit_rate': avg_monthly_hit_rate,
        'avg_monthly_mos_accuracy': avg_monthly_mos_accuracy,
        'avg_spearman': avg_spearman,
        'blind_spot_count': len(blind_spots),
        'blind_spot_tickers': json.dumps(blind_spots),
        'sector_bias_json': json.dumps(sector_bias_raw),
        'sectors_flagged': json.dumps(sectors_flagged),
        'sectors_skipped': json.dumps(sectors_skipped),
        'score_band_json': json.dumps(score_band_data),
        'band_inversion_flag': 1 if band_inversion_flag else 0,
        'consecutive_bias_quarters': json.dumps(consecutive_bias_quarters),
        'total_stocks_evaluated': total_stocks_evaluated,
        'confidence_level': confidence_level,
        'corrections_applied_json': json.dumps(corrections_applied),
        'corrections_blocked_json': json.dumps(corrections_blocked),
    }

    try:
        conn.execute(
            "INSERT OR REPLACE INTO feedback_quarterly "
            "(quarter, portfolio_type, evaluation_window_start, evaluation_window_end, "
            " avg_monthly_top10_return, avg_monthly_hit_rate, avg_monthly_mos_accuracy, "
            " avg_spearman, blind_spot_count, blind_spot_tickers, sector_bias_json, "
            " sectors_flagged, sectors_skipped, score_band_json, band_inversion_flag, "
            " consecutive_bias_quarters, total_stocks_evaluated, confidence_level, "
            " corrections_applied_json, corrections_blocked_json, created_at) "
            "VALUES (:quarter,:portfolio_type,:evaluation_window_start,:evaluation_window_end,"
            " :avg_monthly_top10_return,:avg_monthly_hit_rate,:avg_monthly_mos_accuracy,"
            " :avg_spearman,:blind_spot_count,:blind_spot_tickers,:sector_bias_json,"
            " :sectors_flagged,:sectors_skipped,:score_band_json,:band_inversion_flag,"
            " :consecutive_bias_quarters,:total_stocks_evaluated,:confidence_level,"
            " :corrections_applied_json,:corrections_blocked_json,:created_at)",
            {**review, 'created_at': datetime.utcnow().isoformat()},
        )
        conn.commit()
        print(f"[quarterly] {portfolio_type}/{quarter}: stored "
              f"(confidence={confidence_level}, blind_spots={len(blind_spots)}, "
              f"flagged={len(sectors_flagged)}, applied={len(corrections_applied)}, "
              f"blocked={len(corrections_blocked)})")
    except Exception as exc:
        print(f"[quarterly] ERROR: could not store feedback_quarterly: {exc}")

    top10_str = f"{avg_monthly_top10_return:+.1%}" if avg_monthly_top10_return is not None else "N/A"
    hit_str   = f"{avg_monthly_hit_rate:.1%}" if avg_monthly_hit_rate is not None else "N/A"
    mos_str   = f"{avg_monthly_mos_accuracy:.1%}" if avg_monthly_mos_accuracy is not None else "N/A"
    sp_str    = f"{avg_spearman:.2f}" if avg_spearman is not None else "N/A"
    _notify(
        f"Quarterly Review [{portfolio_type}] — {quarter}: "
        f"Avg Top-10: {top10_str} | Hit Rate: {hit_str} | MoS: {mos_str} | Spearman: {sp_str} | "
        f"Blind Spots: {len(blind_spots)} | Flagged Sectors: {sectors_flagged} | "
        f"Corrections Applied: {len(corrections_applied)} | Blocked: {len(corrections_blocked)} | "
        f"Recurring Unstable: {recurring_unstable_count} | Confidence: {confidence_level}"
    )

    return review
