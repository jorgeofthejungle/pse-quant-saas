# ============================================================
# access_control.py — Subscription Tier Access Control
# PSE Quant SaaS — Dashboard
# ============================================================
# Two tiers:
#   free — educational content + 1 sample stock
#   paid — full access (monthly ₱99 / annual ₱999)
#
# Usage:
#   tier = get_member_tier(discord_id)        # 'free' or 'paid'
#   ok   = check_access(discord_id, feature)  # True / False
# ============================================================

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT))

from db.db_connection import get_connection

# Features available to free tier (no subscription needed)
FREE_FEATURES = {
    'glossary',       # Educational glossary page
    'sample_stock',   # One pre-selected sample analysis (JFC)
    'portal',         # Public portal landing page
    'top3',           # Top 3 stocks (grade only, no score)
    'help',           # /help Discord command
}

# Features requiring paid subscription
PAID_FEATURES = {
    'top10',          # Full top-10 rankings with scores
    'full_rankings',  # All ranked stocks
    'stock_lookup',   # Any stock analysis
    'pdf_reports',    # PDF delivery
    'alerts',         # Price/dividend/earnings alerts
    'discord_bot',    # Full Discord bot responses
}


def get_member_tier(discord_id: str) -> str:
    """
    Returns 'paid' or 'free' for a Discord user.
    'paid' if they have an active subscription in the DB.
    'free' otherwise (no account or expired).
    """
    if not discord_id:
        return 'free'
    conn = get_connection()
    row  = conn.execute("""
        SELECT tier, status FROM members
        WHERE discord_id = ? AND status = 'active'
        LIMIT 1
    """, (str(discord_id),)).fetchone()
    conn.close()

    if not row:
        return 'free'
    # Explicit tier column (Stage 4.3 migration) or infer from status
    tier = row['tier'] if row['tier'] else 'paid'
    return tier if tier in ('free', 'paid') else 'paid'


def check_access(discord_id: str, feature: str) -> bool:
    """
    Returns True if the Discord user has access to the requested feature.
    Paid members get everything. Free members get FREE_FEATURES only.
    """
    if feature in FREE_FEATURES:
        return True
    tier = get_member_tier(discord_id)
    return tier == 'paid'


def get_member_by_discord_id(discord_id: str) -> dict | None:
    """Returns the active member record for a Discord ID, or None."""
    if not discord_id:
        return None
    conn = get_connection()
    row  = conn.execute("""
        SELECT * FROM members
        WHERE discord_id = ? AND status = 'active'
        LIMIT 1
    """, (str(discord_id),)).fetchone()
    conn.close()
    return dict(row) if row else None
