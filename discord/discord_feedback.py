# ============================================================
# discord_feedback.py — Admin Feedback Loop DM Notifications
# PSE Quant SaaS
# ============================================================
# Sends admin DMs for monthly scorecards, quarterly reviews,
# score instability alerts, and correction batch notices.
# All functions use send_dm_text (plain text, not embeds).
# ============================================================

from discord.discord_dm import send_dm_text


def _fmt_pct(val, default='N/A') -> str:
    """Format a float as a signed percentage string, or return default if None."""
    if val is None:
        return default
    return f"{val:+.1%}"


def send_monthly_scorecard_dm(admin_id: str, scorecard_data: dict) -> bool:
    """
    Sends a compact monthly scorecard summary DM to the admin.

    scorecard_data keys:
        month, portfolio_type, top10_avg_return, index_return,
        hit_rate, mos_accuracy, spearman, confidence_level,
        total_matched, score_change_major_count (optional)
    """
    if not admin_id:
        return False
    try:
        d = scorecard_data
        month          = d.get('month', 'Unknown')
        portfolio_type = d.get('portfolio_type', 'Unknown')
        top10_ret      = _fmt_pct(d.get('top10_avg_return'))
        index_ret      = _fmt_pct(d.get('index_return'))
        hit_rate       = _fmt_pct(d.get('hit_rate'))
        mos_acc        = _fmt_pct(d.get('mos_accuracy'))
        spearman       = d.get('spearman')
        spearman_str   = f"{spearman:.2f}" if spearman is not None else 'N/A'
        confidence     = d.get('confidence_level', 'N/A')
        total_matched  = d.get('total_matched', 'N/A')
        major_count    = d.get('score_change_major_count', 0) or 0

        lines = [
            f"Monthly Scorecard — {month} ({portfolio_type})",
            f"Top-10: {top10_ret} vs PSEi {index_ret}",
            f"Hit Rate: {hit_rate} | MoS Accuracy: {mos_acc} | Spearman: {spearman_str}",
            f"Confidence: {confidence} | Matched: {total_matched} stocks",
        ]
        if major_count > 0:
            lines.append(f"⚠ {major_count} major score shifts detected")

        ok, _ = send_dm_text(admin_id, "\n".join(lines))
        return ok
    except Exception:
        return False


def send_quarterly_review_dm(admin_id: str, review_data: dict) -> bool:
    """
    Sends a detailed quarterly review summary DM to the admin.

    review_data keys:
        quarter, portfolio_type, avg_monthly_top10_return, avg_monthly_hit_rate,
        sectors_flagged_list, sectors_skipped_list, blind_spot_count,
        band_inversion_flag, corrections_applied, corrections_blocked,
        confidence_level, total_stocks_evaluated
    """
    if not admin_id:
        return False
    try:
        d = review_data
        quarter        = d.get('quarter', 'Unknown')
        portfolio_type = d.get('portfolio_type', 'Unknown')
        avg_return     = _fmt_pct(d.get('avg_monthly_top10_return'))
        avg_hit_rate   = _fmt_pct(d.get('avg_monthly_hit_rate'))
        flagged        = d.get('sectors_flagged_list', [])
        skipped        = d.get('sectors_skipped_list', [])
        flagged_str    = ', '.join(flagged) if flagged else 'None'
        skipped_str    = ', '.join(skipped) if skipped else 'None'
        blind_spots    = d.get('blind_spot_count', 0)
        band_inversion = d.get('band_inversion_flag', False)
        corrections_n  = d.get('corrections_applied', 0)
        corrections_m  = d.get('corrections_blocked', 0)
        confidence     = d.get('confidence_level', 'N/A')
        total_stocks   = d.get('total_stocks_evaluated', 'N/A')

        lines = [
            f"Quarterly Review — {quarter} ({portfolio_type})",
            f"Avg Top-10: {avg_return} | Hit Rate: {avg_hit_rate}",
            f"Sectors flagged: {flagged_str} | Skipped: {skipped_str}",
            f"Blind spots: {blind_spots} | Band inversion: {band_inversion}",
            f"Corrections applied: {corrections_n} | Blocked: {corrections_m}",
            f"Confidence: {confidence} | Stocks evaluated: {total_stocks}",
        ]

        ok, _ = send_dm_text(admin_id, "\n".join(lines))
        return ok
    except Exception:
        return False


def send_score_instability_alert(
    admin_id: str,
    ticker: str,
    consecutive_months: int,
    severity: str,
    magnitude: float | None = None,
) -> bool:
    """
    Immediate DM for a ticker that has triggered score_change_flag for multiple
    consecutive months. Not batched — sent immediately on detection.
    """
    if not admin_id:
        return False
    try:
        magnitude_str = f" | Magnitude: {magnitude:.1f} pts" if magnitude is not None else ""
        lines = [
            f"Score Instability Alert — {ticker}",
            f"Triggered score_change_flag for {consecutive_months} consecutive months",
            f"Latest severity: {severity}{magnitude_str}",
            "Immediate review recommended — do not wait for next monthly review.",
        ]
        ok, _ = send_dm_text(admin_id, "\n".join(lines))
        return ok
    except Exception:
        return False


def send_correction_batch_dm(admin_id: str, corrections: list[dict]) -> bool:
    """
    Batches multiple correction notifications into a single DM.

    Each correction dict keys:
        sector, layer, adjustment, cumulative, quarter
    """
    if not admin_id:
        return False
    try:
        lines = [f"Corrections Applied — {len(corrections)} sector adjustments"]
        for c in corrections:
            sector     = c.get('sector', 'Unknown')
            layer      = c.get('layer', 'Unknown')
            adjustment = _fmt_pct(c.get('adjustment'))
            cumulative = _fmt_pct(c.get('cumulative'))
            quarter    = c.get('quarter', 'Unknown')
            lines.append(
                f"{sector} ({layer}): {adjustment} (cumulative: {cumulative}) — {quarter}"
            )
        ok, _ = send_dm_text(admin_id, "\n".join(lines))
        return ok
    except Exception:
        return False


def send_correction_expiry_dm(admin_id: str, expired_corrections: list[dict]) -> bool:
    """
    Batches expiry notices for corrections that have lapsed after 4 quarters.

    Each expired_correction dict keys:
        sector, layer, cumulative
    """
    if not admin_id:
        return False
    try:
        lines = [f"Corrections Expired: {len(expired_corrections)} entries lapsed"]
        for c in expired_corrections:
            sector     = c.get('sector', 'Unknown')
            layer      = c.get('layer', 'Unknown')
            cumulative = _fmt_pct(c.get('cumulative'))
            lines.append(
                f"{sector}/{layer} expired after 4 quarters (was {cumulative})"
            )
        ok, _ = send_dm_text(admin_id, "\n".join(lines))
        return ok
    except Exception:
        return False
