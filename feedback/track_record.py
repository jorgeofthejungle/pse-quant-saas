# feedback/track_record.py — Track Record Module (Tier 3 Presentation Layer)
# Computes rolling performance windows from monthly scorecard data.
# Pure deterministic math — no AI calls, no scipy.
# All return/rate values stored as decimals (e.g. 0.05 = 5%).

import statistics
from datetime import date, datetime
from db.db_connection import get_connection

PORTFOLIO_TYPES = ['dividend', 'value']
PERIOD_MONTHS   = {'1m': 1, '3m': 3, '6m': 6, '12m': 12}


# ── Index price helpers ───────────────────────────────────────────────────────

def _get_index_close(target_date: str, direction: str) -> float | None:
    """Return PSEi close nearest to target_date. direction='fwd' or 'back'."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        if direction == 'fwd':
            cur.execute(
                "SELECT close FROM index_prices WHERE index_name='PSEi' AND date >= ? "
                "ORDER BY date ASC LIMIT 1",
                (target_date,),
            )
        else:
            cur.execute(
                "SELECT close FROM index_prices WHERE index_name='PSEi' AND date <= ? "
                "ORDER BY date DESC LIMIT 1",
                (target_date,),
            )
        row = cur.fetchone()
        return float(row[0]) if row else None
    finally:
        conn.close()


def _get_index_return(start_date: str, end_date: str) -> float | None:
    """Return (close_end - close_start) / close_start for PSEi, or None."""
    close_start = _get_index_close(start_date, 'fwd')
    close_end   = _get_index_close(end_date,   'back')
    if close_start is None or close_end is None or close_start == 0:
        return None
    return (close_end - close_start) / close_start


# ── Monthly data loader ───────────────────────────────────────────────────────

def _load_monthly_rows(portfolio_type: str, evaluation_date: str, n: int) -> list[dict]:
    """Load up to N monthly scorecard rows ending at/before evaluation_date."""
    eval_month = evaluation_date[:7]  # YYYY-MM
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT month, top10_avg_return, top10_vs_index,
                   hit_rate_positive, mos_direction_accuracy, spearman_correlation
            FROM   feedback_monthly
            WHERE  portfolio_type = ?
              AND  month <= ?
            ORDER  BY month DESC
            LIMIT  ?
            """,
            (portfolio_type, eval_month, n),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


# ── Metric computation ────────────────────────────────────────────────────────

def _safe_mean(values: list) -> float | None:
    cleaned = [v for v in values if v is not None]
    return statistics.mean(cleaned) if cleaned else None


def _compute_metrics(rows: list[dict], n: int, evaluation_date: str) -> dict:
    """Compute all rolling metrics for a window of monthly rows."""
    returns     = [r['top10_avg_return']        for r in rows]
    hit_rates   = [r['hit_rate_positive']       for r in rows]
    mos_vals    = [r['mos_direction_accuracy']  for r in rows]
    spearmans   = [r['spearman_correlation']    for r in rows]

    # Averages (skip NULL)
    top10_avg_return = _safe_mean(returns)
    hit_rate         = _safe_mean(hit_rates)
    mos_accuracy     = _safe_mean(mos_vals)
    avg_spearman     = _safe_mean(spearmans)

    # Cumulative compounded return (skip NULL months)
    valid_returns = [r for r in returns if r is not None]
    if valid_returns:
        product = 1.0
        for r in valid_returns:
            product *= (1.0 + r)
        top10_cumulative_return = product - 1.0
    else:
        top10_cumulative_return = None

    # Index return over the full window
    if rows:
        earliest_month = min(r['month'] for r in rows)
        start_date = earliest_month + '-01'
        index_cumulative_return = _get_index_return(start_date, evaluation_date)
    else:
        index_cumulative_return = None

    # Alpha vs index
    if top10_cumulative_return is not None and index_cumulative_return is not None:
        top10_vs_index = top10_cumulative_return - index_cumulative_return
    else:
        top10_vs_index = None

    # Best / worst month
    best_month_return  = max(valid_returns) if valid_returns else None
    worst_month_return = min(valid_returns) if valid_returns else None

    # Consecutive months outperforming (proxy: top10_avg_return > 0, from most recent)
    streak = 0
    for r in returns:  # rows already sorted DESC
        if r is not None and r > 0:
            streak += 1
        else:
            break
    consecutive_months_outperforming_index = streak

    # Positive Spearman ratio
    sp_clean = [s for s in spearmans if s is not None]
    positive_spearman_ratio = (
        sum(1 for s in sp_clean if s > 0) / len(sp_clean) if sp_clean else None
    )

    # Data completeness
    total_months_tracked  = len(rows)
    months_with_return    = sum(1 for r in returns if r is not None)
    data_completeness_pct = months_with_return / n if n > 0 else 0.0

    return {
        'top10_avg_return':                       top10_avg_return,
        'top10_cumulative_return':                top10_cumulative_return,
        'index_cumulative_return':                index_cumulative_return,
        'top10_vs_index':                         top10_vs_index,
        'hit_rate':                               hit_rate,
        'mos_accuracy':                           mos_accuracy,
        'total_months_tracked':                   total_months_tracked,
        'consecutive_months_outperforming_index': consecutive_months_outperforming_index,
        'best_month_return':                      best_month_return,
        'worst_month_return':                     worst_month_return,
        'avg_spearman':                           avg_spearman,
        'positive_spearman_ratio':                positive_spearman_ratio,
        'data_completeness_pct':                  data_completeness_pct,
    }


# ── Publishability gate ───────────────────────────────────────────────────────

def _apply_gate(metrics: dict, period_type: str, n: int) -> tuple[int, str | None]:
    """Returns (publishable, publish_reason)."""
    dc   = metrics['data_completeness_pct']
    wm   = metrics['worst_month_return']
    hr   = metrics['hit_rate']
    tvi  = metrics['top10_vs_index']
    tm   = metrics['total_months_tracked']

    if period_type == '1m':
        publishable = 1 if dc > 0 else 0
        if not publishable:
            return 0, 'Insufficient data: no monthly data available'
        # Still check crash gate
        if wm is not None and wm < -0.15:
            return 0, f'Unstable: worst month return < -15% ({wm:.1%})'
        return 1, None

    # 3m / 6m / 12m
    reasons = []
    pub = 1

    if tm < n:
        pub = 0
        reasons.append(f'Insufficient data: {tm}/{n} months tracked')

    if pub == 1:
        hr_ok  = hr  is not None and hr  > 0.40
        tvi_ok = tvi is not None and tvi > 0
        if not (hr_ok or tvi_ok):
            pub = 0
            hr_str  = f'{hr:.2f}'  if hr  is not None else 'N/A'
            tvi_str = f'{tvi:.4f}' if tvi is not None else 'N/A'
            reasons.append(f'Below threshold: hit_rate {hr_str}, top10_vs_index {tvi_str}')

    if wm is not None and wm < -0.15:
        pub = 0
        reasons.append(f'Unstable: worst month return < -15% ({wm:.1%})')

    return pub, ('; '.join(reasons) if reasons else None)


# ── Main entry point ──────────────────────────────────────────────────────────

def compute_track_record(evaluation_date: str | None = None) -> int:
    """Compute rolling track-record windows and persist to feedback_track_record.
    Returns count of rows inserted/replaced."""
    if evaluation_date is None:
        evaluation_date = date.today().isoformat()

    now_ts  = datetime.utcnow().isoformat()
    conn    = get_connection()
    inserted = 0

    try:
        cur = conn.cursor()
        for period_type, n in PERIOD_MONTHS.items():
            for portfolio_type in PORTFOLIO_TYPES:
                rows    = _load_monthly_rows(portfolio_type, evaluation_date, n)
                metrics = _compute_metrics(rows, n, evaluation_date)
                pub, reason = _apply_gate(metrics, period_type, n)

                cur.execute(
                    """
                    INSERT OR REPLACE INTO feedback_track_record (
                        period_type, portfolio_type, evaluation_date,
                        top10_avg_return, top10_cumulative_return,
                        index_cumulative_return, top10_vs_index,
                        hit_rate, mos_accuracy,
                        total_months_tracked,
                        consecutive_months_outperforming_index,
                        best_month_return, worst_month_return,
                        avg_spearman, positive_spearman_ratio,
                        data_completeness_pct,
                        publishable, publish_reason, created_at
                    ) VALUES (
                        ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                    )
                    """,
                    (
                        period_type, portfolio_type, evaluation_date,
                        metrics['top10_avg_return'],
                        metrics['top10_cumulative_return'],
                        metrics['index_cumulative_return'],
                        metrics['top10_vs_index'],
                        metrics['hit_rate'],
                        metrics['mos_accuracy'],
                        metrics['total_months_tracked'],
                        metrics['consecutive_months_outperforming_index'],
                        metrics['best_month_return'],
                        metrics['worst_month_return'],
                        metrics['avg_spearman'],
                        metrics['positive_spearman_ratio'],
                        metrics['data_completeness_pct'],
                        pub, reason, now_ts,
                    ),
                )
                inserted += 1

        conn.commit()
    except Exception as exc:
        print(f"[track_record] ERROR during compute_track_record: {exc}")
    finally:
        conn.close()

    return inserted


# ── Query helper ──────────────────────────────────────────────────────────────

def get_track_record(
    portfolio_type: str,
    period_type: str | None = None,
) -> list[dict]:
    """Return publishable track-record rows for a portfolio, sorted by evaluation_date DESC."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        if period_type:
            cur.execute(
                """
                SELECT * FROM feedback_track_record
                WHERE  portfolio_type = ? AND period_type = ? AND publishable = 1
                ORDER  BY evaluation_date DESC
                """,
                (portfolio_type, period_type),
            )
        else:
            cur.execute(
                """
                SELECT * FROM feedback_track_record
                WHERE  portfolio_type = ? AND publishable = 1
                ORDER  BY evaluation_date DESC
                """,
                (portfolio_type,),
            )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()
