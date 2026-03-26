# feedback/monthly_scorecard.py — Monthly Performance Scorecard (Tier 1)
# Measures how well the scoring model predicted stock price movements each month.
# Pure deterministic math — no AI calls, no scipy.
# All return/rate values stored as decimals (e.g. 0.05 = 5%).

import statistics
from datetime import date, datetime, timedelta
from db.db_connection import get_connection
from config import (
    SCORE_CHANGE_MINOR_THRESHOLD,
    SCORE_CHANGE_MAJOR_THRESHOLD,
    MOS_HIT_THRESHOLD,
    THIN_MONTH_THRESHOLD,
    SCORE_INSTABILITY_ALERT_MONTHS,
)

PORTFOLIO_TYPES = ['dividend', 'value']


# ── Date helpers ─────────────────────────────────────────────────────────────

def _month_bounds(month: str) -> tuple[str, str]:
    """(first_day_of_month, first_day_of_next_month) as YYYY-MM-DD."""
    year, mon = int(month[:4]), int(month[5:7])
    t_minus1 = date(year, mon, 1).isoformat()
    t_date = date(year + 1, 1, 1).isoformat() if mon == 12 else date(year, mon + 1, 1).isoformat()
    return t_minus1, t_date


def _previous_month() -> str:
    """YYYY-MM string for the previous calendar month."""
    first_this_month = date.today().replace(day=1)
    return (first_this_month - timedelta(days=1)).strftime('%Y-%m')


# ── Spearman rank correlation (no scipy) ────────────────────────────────────

def _rank_with_ties(vals: list) -> list:
    """Ranks with average tie-breaking (ascending)."""
    indexed = sorted(enumerate(vals), key=lambda x: x[1])
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(indexed):
        j = i
        while j < len(indexed) - 1 and indexed[j + 1][1] == indexed[j][1]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def _spearman(xs: list, ys: list) -> float:
    """Pearson on ranked values = Spearman rho."""
    rx = _rank_with_ties(xs)
    ry = _rank_with_ties(ys)
    n = len(rx)
    mean_rx = sum(rx) / n
    mean_ry = sum(ry) / n
    num = sum((rx[i] - mean_rx) * (ry[i] - mean_ry) for i in range(n))
    den = (
        sum((rx[i] - mean_rx) ** 2 for i in range(n))
        * sum((ry[i] - mean_ry) ** 2 for i in range(n))
    ) ** 0.5
    return num / den if den != 0 else 0.0


# ── Notification helper ──────────────────────────────────────────────────────

def _notify(msg: str) -> None:
    try:
        from feedback import discord_feedback  # type: ignore
        discord_feedback.send_admin_dm(msg)
    except Exception:
        print(f"[scorecard] {msg}")


# ── Consecutive flag counter ─────────────────────────────────────────────────

def _count_consecutive_flags(conn, ticker: str, portfolio_type: str, before_month: str) -> int:
    """Count prior consecutive flagged months, stopping at first non-flagged."""
    rows = conn.execute(
        "SELECT month, score_change_flag FROM feedback_stock_returns "
        "WHERE ticker = ? AND portfolio_type = ? AND month < ? "
        "ORDER BY month DESC",
        (ticker, portfolio_type, before_month),
    ).fetchall()
    count = 0
    for row in rows:
        if row['score_change_flag'] == 1:
            count += 1
        else:
            break
    return count


# ── Step 1 + 2: Load snapshots and compute match sets ────────────────────────

def _load_snapshots(conn, snapshot_date: str, portfolio_type: str) -> dict:
    """{ticker: row_dict} for a given snapshot_date + portfolio_type."""
    rows = conn.execute(
        "SELECT * FROM feedback_snapshots "
        "WHERE snapshot_date = ? AND portfolio_type = ?",
        (snapshot_date, portfolio_type),
    ).fetchall()
    return {row['ticker']: dict(row) for row in rows}


# ── Step 4 helper: index return ──────────────────────────────────────────────

def _index_return(conn, t_minus1: str, t_date: str) -> float | None:
    """PSEi return over the month window as decimal, or None if missing."""
    row_start = conn.execute(
        "SELECT close FROM index_prices WHERE date <= ? ORDER BY date DESC LIMIT 1",
        (t_minus1,),
    ).fetchone()
    row_end = conn.execute(
        "SELECT close FROM index_prices WHERE date <= ? ORDER BY date DESC LIMIT 1",
        (t_date,),
    ).fetchone()
    if not row_start or not row_end:
        return None
    c_start = float(row_start['close'])
    c_end = float(row_end['close'])
    if c_start == 0:
        return None
    return (c_end - c_start) / c_start


# ── Step 3 helper: check for new financials ──────────────────────────────────

def _has_new_financials(conn, ticker: str, t_minus1: str, t_date: str) -> bool:
    """True if a financials row for this ticker was updated within the window."""
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM financials "
        "WHERE ticker = ? AND updated_at > ? AND updated_at <= ?",
        (ticker, t_minus1, t_date),
    ).fetchone()
    return (row['cnt'] or 0) > 0


# ── Main scorecard function ──────────────────────────────────────────────────

def run_monthly_scorecard(month: str | None = None) -> dict | None:
    """
    Run the 14-step monthly scorecard algorithm for all portfolio types.

    Args:
        month: YYYY-MM string. Defaults to previous month.

    Returns:
        Dict mapping portfolio_type -> scorecard_dict, or None on failure.
    """
    if month is None:
        month = _previous_month()

    t_minus1, t_date = _month_bounds(month)
    print(f"[scorecard] Running scorecard for month={month} "
          f"(T-1={t_minus1}, T={t_date})")

    try:
        conn = get_connection()
    except Exception as exc:
        print(f"[scorecard] ERROR: cannot open DB: {exc}")
        return None

    results = {}
    try:
        for portfolio_type in PORTFOLIO_TYPES:
            result = _run_for_portfolio(conn, month, portfolio_type, t_minus1, t_date)
            if result is not None:
                results[portfolio_type] = result
    except Exception as exc:
        print(f"[scorecard] ERROR: unexpected failure: {exc}")
        return None
    finally:
        conn.close()
    return results if results else None


def _run_for_portfolio(
    conn,
    month: str,
    portfolio_type: str,
    t_minus1: str,
    t_date: str,
) -> dict | None:
    """Run all 14 steps for a single portfolio_type. Returns scorecard dict or None."""

    # ── Step 1: Load snapshots ──────────────────────────────────────────────
    snap_prev = _load_snapshots(conn, t_minus1, portfolio_type)
    snap_curr = _load_snapshots(conn, t_date, portfolio_type)

    if not snap_prev or not snap_curr:
        missing = t_minus1 if not snap_prev else t_date
        print(f"[scorecard] {portfolio_type}: no snapshot for {missing} — skipping.")
        return None

    # ── Step 2: Data integrity ──────────────────────────────────────────────
    total_previous = len(snap_prev)
    total_current = len(snap_curr)
    matched_tickers = [t for t in snap_prev if t in snap_curr]
    total_matched = len(matched_tickers)
    match_rate_pct = total_matched / max(total_previous, total_current) \
        if max(total_previous, total_current) > 0 else 0.0

    print(f"[scorecard] {portfolio_type}: T-1={total_previous}, T={total_current}, "
          f"matched={total_matched} (match_rate={match_rate_pct:.1%})")

    if total_matched == 0:
        print(f"[scorecard] {portfolio_type}: no matched stocks — skipping.")
        return None

    # ── Step 3: Compute returns per matched stock ──────────────────────────
    stock_returns = []

    for ticker in matched_tickers:
        prev = snap_prev[ticker]
        curr = snap_curr[ticker]

        price_start = prev.get('price_at_snapshot')
        price_end = curr.get('price_at_snapshot')
        score_start = prev.get('score')
        score_end = curr.get('score')

        if price_start is None or price_end is None or price_start == 0:
            continue  # can't compute return — skip

        return_pct = (float(price_end) - float(price_start)) / float(price_start)
        score_start_f = float(score_start) if score_start is not None else None
        score_end_f = float(score_end) if score_end is not None else None

        # Score change flag logic
        score_change_flag = False
        score_change_severity = None
        score_change_magnitude = None

        if score_start_f is not None and score_end_f is not None:
            score_delta = abs(score_end_f - score_start_f)
            if score_delta > SCORE_CHANGE_MINOR_THRESHOLD:
                new_financials = _has_new_financials(conn, ticker, t_minus1, t_date)
                if not new_financials:
                    score_change_flag = True
                    score_change_magnitude = score_delta
                    if score_delta > SCORE_CHANGE_MAJOR_THRESHOLD:
                        score_change_severity = 'major'
                    else:
                        score_change_severity = 'minor'

        # Consecutive flag months (prior months only)
        consecutive_months = _count_consecutive_flags(conn, ticker, portfolio_type, month)

        was_top10 = int(prev.get('is_top10') or 0)
        rank_at_start = prev.get('rank')

        try:
            conn.execute(
                "INSERT OR REPLACE INTO feedback_stock_returns "
                "(ticker, month, portfolio_type, score_at_start, price_start, price_end, "
                " return_pct, rank_at_start, was_top10, score_change_flag, "
                " score_change_severity, score_change_magnitude, consecutive_flag_months, "
                " created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ticker, month, portfolio_type,
                    score_start_f, float(price_start), float(price_end),
                    return_pct, rank_at_start, was_top10,
                    1 if score_change_flag else 0,
                    score_change_severity, score_change_magnitude,
                    consecutive_months,
                    datetime.utcnow().isoformat(),
                ),
            )
        except Exception as exc:
            print(f"[scorecard] WARNING: could not insert return for {ticker}: {exc}")

        stock_returns.append({
            'ticker': ticker,
            'return_pct': return_pct,
            'score_start': score_start_f,
            'mos_pct': prev.get('mos_pct'),
            'iv_estimate': prev.get('iv_estimate'),
            'was_top10': was_top10,
            'score_change_flag': score_change_flag,
            'score_change_severity': score_change_severity,
        })

    conn.commit()

    if not stock_returns:
        print(f"[scorecard] {portfolio_type}: no valid return records — skipping.")
        return None

    total_computed = len(stock_returns)

    # ── Step 4: Top-10 performance ─────────────────────────────────────────
    top10_stocks = [s for s in stock_returns if s['was_top10'] == 1]
    top10_avg_return = (
        statistics.mean(s['return_pct'] for s in top10_stocks)
        if top10_stocks else None
    )

    idx_return = _index_return(conn, t_minus1, t_date)
    if top10_avg_return is not None and idx_return is not None:
        top10_vs_index = top10_avg_return - idx_return
    else:
        top10_vs_index = None

    # ── Step 5: Market baseline ────────────────────────────────────────────
    positive_count = sum(1 for s in stock_returns if s['return_pct'] > 0)
    market_positive_rate = positive_count / total_computed

    # ── Step 6: Hit rate (MoS-based) ──────────────────────────────────────
    mos_eligible = [s for s in stock_returns if s['mos_pct'] is not None]
    hit_rate_positive = None
    if mos_eligible:
        correct = 0
        for s in mos_eligible:
            predicted_up = float(s['mos_pct']) > MOS_HIT_THRESHOLD
            actual_up = s['return_pct'] > 0
            if predicted_up == actual_up:
                correct += 1
        hit_rate_positive = correct / len(mos_eligible)

    # ── Step 7: MoS direction accuracy ────────────────────────────────────
    mos_direction_accuracy = None
    if mos_eligible:
        correct_dir = 0
        for s in mos_eligible:
            expected_dir = 'up' if float(s['mos_pct']) > 0 else 'down'
            actual_dir = 'up' if s['return_pct'] > 0 else 'down'
            if expected_dir == actual_dir:
                correct_dir += 1
        mos_direction_accuracy = correct_dir / len(mos_eligible)

    iv_stocks = [s for s in stock_returns if s['iv_estimate'] is not None]
    iv_coverage_pct = len(iv_stocks) / total_previous if total_previous > 0 else 0.0

    # ── Step 8: Spearman rank correlation ─────────────────────────────────
    spearman_correlation = None
    scored_stocks = [s for s in stock_returns if s['score_start'] is not None]
    if len(scored_stocks) >= 3:
        scores_list = [s['score_start'] for s in scored_stocks]
        returns_list = [s['return_pct'] for s in scored_stocks]
        try:
            spearman_correlation = _spearman(scores_list, returns_list)
        except Exception as exc:
            print(f"[scorecard] WARNING: Spearman failed: {exc}")

    # ── Step 9: Score separation ───────────────────────────────────────────
    gainers = [s for s in stock_returns if s['return_pct'] > 0 and s['score_start'] is not None]
    losers = [s for s in stock_returns if s['return_pct'] <= 0 and s['score_start'] is not None]
    avg_score_gainers = statistics.mean(s['score_start'] for s in gainers) if gainers else None
    avg_score_losers = statistics.mean(s['score_start'] for s in losers) if losers else None
    score_separation_power = (
        avg_score_gainers - avg_score_losers
        if avg_score_gainers is not None and avg_score_losers is not None
        else None
    )

    # ── Step 10: Score stability aggregation ──────────────────────────────
    flagged = [s for s in stock_returns if s['score_change_flag']]
    score_change_flag_count = len(flagged)
    score_change_minor_count = sum(1 for s in flagged if s['score_change_severity'] == 'minor')
    score_change_major_count = sum(1 for s in flagged if s['score_change_severity'] == 'major')

    # ── Step 11: Confidence level ──────────────────────────────────────────
    if (
        total_computed >= 30
        and top10_vs_index is not None and top10_vs_index > 0
        and hit_rate_positive is not None and hit_rate_positive > 0.5
        and spearman_correlation is not None and spearman_correlation > 0
    ):
        confidence_level = 'high'
    elif total_computed >= THIN_MONTH_THRESHOLD:
        confidence_level = 'medium'
    else:
        confidence_level = 'low'

    # ── Step 12: Store results ─────────────────────────────────────────────
    scorecard = {
        'month': month,
        'portfolio_type': portfolio_type,
        'total_previous': total_previous,
        'total_current': total_current,
        'total_matched': total_computed,
        'match_rate_pct': match_rate_pct,
        'top10_avg_return': top10_avg_return,
        'index_return': idx_return,        # informational only — not stored in DB
        'top10_vs_index': top10_vs_index,
        'market_positive_rate': market_positive_rate,
        'hit_rate_positive': hit_rate_positive,
        'mos_direction_accuracy': mos_direction_accuracy,
        'iv_coverage_pct': iv_coverage_pct,
        'spearman_correlation': spearman_correlation,
        'avg_score_of_gainers': avg_score_gainers,
        'avg_score_of_losers': avg_score_losers,
        'score_separation_power': score_separation_power,
        'score_change_flag_count': score_change_flag_count,
        'score_change_minor_count': score_change_minor_count,
        'score_change_major_count': score_change_major_count,
        'confidence_level': confidence_level,
        'created_at': datetime.utcnow().isoformat(),
    }

    try:
        conn.execute(
            "INSERT OR REPLACE INTO feedback_monthly "
            "(month, portfolio_type, total_previous, total_current, total_matched, "
            " match_rate_pct, top10_avg_return, top10_vs_index, "
            " market_positive_rate, hit_rate_positive, mos_direction_accuracy, "
            " iv_coverage_pct, spearman_correlation, avg_score_of_gainers, "
            " avg_score_of_losers, score_separation_power, score_change_flag_count, "
            " score_change_minor_count, score_change_major_count, confidence_level, "
            " created_at) "
            "VALUES (:month, :portfolio_type, :total_previous, :total_current, "
            " :total_matched, :match_rate_pct, :top10_avg_return, "
            " :top10_vs_index, :market_positive_rate, :hit_rate_positive, "
            " :mos_direction_accuracy, :iv_coverage_pct, :spearman_correlation, "
            " :avg_score_of_gainers, :avg_score_of_losers, :score_separation_power, "
            " :score_change_flag_count, :score_change_minor_count, "
            " :score_change_major_count, :confidence_level, :created_at)",
            scorecard,
        )
        conn.commit()
        print(f"[scorecard] {portfolio_type}: scorecard stored "
              f"(confidence={confidence_level})")
    except Exception as exc:
        print(f"[scorecard] ERROR: could not store feedback_monthly: {exc}")

    # ── Step 13: Notifications ─────────────────────────────────────────────
    top10_str = f"{top10_avg_return:+.1%}" if top10_avg_return is not None else "N/A"
    idx_str = f"{idx_return:+.1%}" if idx_return is not None else "N/A"
    hit_str = f"{hit_rate_positive:.1%}" if hit_rate_positive is not None else "N/A"
    mos_str = f"{mos_direction_accuracy:.1%}" if mos_direction_accuracy is not None else "N/A"
    sp_str = f"{spearman_correlation:.2f}" if spearman_correlation is not None else "N/A"

    summary_msg = (
        f"Monthly Scorecard [{portfolio_type}] — {month}: "
        f"Top-10: {top10_str} vs PSEi {idx_str}. "
        f"Hit Rate: {hit_str}. MoS Accuracy: {mos_str}. Spearman: {sp_str}"
    )
    _notify(summary_msg)

    if score_change_major_count > 0:
        _notify(
            f"WARNING: {score_change_major_count} stocks had major unexplained "
            f"score shifts in {portfolio_type} ({month}). Review recommended."
        )

    # ── Step 14: Consecutive flag alerts ──────────────────────────────────
    try:
        unstable_rows = conn.execute(
            "SELECT ticker, consecutive_flag_months, score_change_severity "
            "FROM feedback_stock_returns "
            "WHERE month = ? AND portfolio_type = ? "
            "AND consecutive_flag_months >= ?",
            (month, portfolio_type, SCORE_INSTABILITY_ALERT_MONTHS),
        ).fetchall()
        for row in unstable_rows:
            alert_msg = (
                f"Score Instability Alert — {row['ticker']} has triggered "
                f"score_change_flag for {row['consecutive_flag_months']} consecutive "
                f"months (latest: {row['score_change_severity']}). "
                f"Immediate review recommended."
            )
            _notify(alert_msg)
    except Exception as exc:
        print(f"[scorecard] WARNING: could not check consecutive flags: {exc}")

    return scorecard


# ── Public read helper ───────────────────────────────────────────────────────

def get_scorecard(month: str, portfolio_type: str) -> dict | None:
    """Retrieve a stored monthly scorecard row as dict, or None if not found."""
    try:
        conn = get_connection()
    except Exception as exc:
        print(f"[scorecard] ERROR: cannot open DB: {exc}")
        return None

    try:
        row = conn.execute(
            "SELECT * FROM feedback_monthly WHERE month = ? AND portfolio_type = ?",
            (month, portfolio_type),
        ).fetchone()
        return dict(row) if row else None
    except Exception as exc:
        print(f"[scorecard] ERROR: get_scorecard failed: {exc}")
        return None
    finally:
        conn.close()
