# ============================================================
# db_members.py — Members, Subscriptions & Activity Log DB Ops
# PSE Quant SaaS — Dashboard
# ============================================================

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'db'))
sys.path.insert(0, str(ROOT))

from db.db_connection import get_connection


# ── Expiry auto-update ────────────────────────────────────────

def expire_overdue_members():
    """
    Marks members as 'expired' if expiry_date < today.
    Called on every page load (lightweight query).
    Returns the number of members just expired.
    """
    today = datetime.now().strftime('%Y-%m-%d')
    conn  = get_connection()
    cur   = conn.execute("""
        UPDATE members SET status = 'expired'
        WHERE status = 'active'
          AND expiry_date IS NOT NULL
          AND expiry_date < ?
    """, (today,))
    conn.commit()
    changed = cur.rowcount
    conn.close()
    return changed


# ── Member CRUD ───────────────────────────────────────────────

def get_all_members(status_filter: str = None) -> list:
    """
    Returns all members, optionally filtered by status.
    status_filter: 'active', 'expired', 'cancelled', or None for all.
    """
    conn  = get_connection()
    query = "SELECT * FROM members"
    args  = ()
    if status_filter:
        query += " WHERE status = ?"
        args   = (status_filter,)
    query += " ORDER BY expiry_date ASC"
    rows  = conn.execute(query, args).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_member(member_id: int) -> dict | None:
    """Returns a single member by ID, or None if not found."""
    conn = get_connection()
    row  = conn.execute(
        "SELECT * FROM members WHERE id = ?", (member_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def add_member(discord_name: str, plan: str,
               discord_id: str = None, email: str = None,
               notes: str = None) -> int:
    """
    Inserts a new member with status='active'.
    Calculates expiry_date based on plan (monthly=30d, annual=365d).
    Returns the new member's ID.
    """
    today   = datetime.now().strftime('%Y-%m-%d')
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    days    = 365 if plan == 'annual' else 30
    expiry  = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')

    conn = get_connection()
    cur  = conn.execute("""
        INSERT INTO members
            (discord_id, discord_name, email, plan, status,
             joined_date, expiry_date, notes, created_at)
        VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?)
    """, (discord_id, discord_name, email, plan,
          today, expiry, notes, now_str))
    conn.commit()
    member_id = cur.lastrowid
    conn.close()
    log_activity('member', 'member_added',
                 f"{discord_name} ({plan}) joined", status='ok')
    return member_id


def update_member(member_id: int, discord_name: str = None,
                  discord_id: str = None, email: str = None,
                  plan: str = None, notes: str = None):
    """Updates editable member fields. None values are left unchanged."""
    conn = get_connection()
    conn.execute("""
        UPDATE members SET
            discord_name = COALESCE(?, discord_name),
            discord_id   = COALESCE(?, discord_id),
            email        = COALESCE(?, email),
            plan         = COALESCE(?, plan),
            notes        = COALESCE(?, notes)
        WHERE id = ?
    """, (discord_name, discord_id, email, plan, notes, member_id))
    conn.commit()
    conn.close()


def extend_member(member_id: int, days: int, source: str = 'manual'):
    """
    Extends the member's expiry_date by `days` from today or current expiry
    (whichever is later), and resets status to 'active'.
    """
    today = datetime.now().strftime('%Y-%m-%d')
    conn  = get_connection()
    row   = conn.execute(
        "SELECT expiry_date, discord_name FROM members WHERE id = ?",
        (member_id,)
    ).fetchone()
    if not row:
        conn.close()
        return

    base   = max(today, row['expiry_date'] or today)
    new_ex = (datetime.strptime(base, '%Y-%m-%d') + timedelta(days=days)
              ).strftime('%Y-%m-%d')

    conn.execute("""
        UPDATE members SET expiry_date = ?, status = 'active'
        WHERE id = ?
    """, (new_ex, member_id))
    conn.commit()
    conn.close()
    log_activity('member', 'subscription_extended',
                 f"{row['discord_name']}: +{days} days via {source} (new expiry {new_ex})")


def cancel_member(member_id: int):
    """Sets a member's status to 'cancelled'."""
    conn = get_connection()
    row  = conn.execute(
        "SELECT discord_name FROM members WHERE id = ?", (member_id,)
    ).fetchone()
    conn.execute(
        "UPDATE members SET status = 'cancelled' WHERE id = ?", (member_id,)
    )
    conn.commit()
    conn.close()
    if row:
        log_activity('member', 'member_cancelled', row['discord_name'])


# ── Subscriptions ─────────────────────────────────────────────

def record_payment(member_id: int, amount: float, plan: str,
                   payment_method: str = 'manual',
                   payment_id: str = None) -> int:
    """
    Records a payment and extends the member's subscription.
    Returns the subscription record ID.
    """
    today  = datetime.now().strftime('%Y-%m-%d')
    days   = 365 if plan == 'annual' else 30
    p_end  = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')

    conn = get_connection()
    cur  = conn.execute("""
        INSERT INTO subscriptions
            (member_id, payment_id, amount, plan, status, payment_method,
             paid_date, period_start, period_end)
        VALUES (?, ?, ?, ?, 'paid', ?, ?, ?, ?)
    """, (member_id, payment_id, amount, plan, payment_method,
          today, today, p_end))
    conn.commit()
    sub_id = cur.lastrowid

    # Get member name for log
    row = conn.execute(
        "SELECT discord_name FROM members WHERE id = ?", (member_id,)
    ).fetchone()
    conn.close()

    extend_member(member_id, days, source=payment_method)
    name = row['discord_name'] if row else f'member#{member_id}'
    log_activity('payment', 'payment_received',
                 f"PHP {amount:.2f} from {name} via {payment_method}")
    return sub_id


def get_member_subscriptions(member_id: int) -> list:
    """Returns all payment records for a member, newest first."""
    conn  = get_connection()
    rows  = conn.execute("""
        SELECT * FROM subscriptions
        WHERE member_id = ?
        ORDER BY paid_date DESC
    """, (member_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_expiring_soon(days: int = 7) -> list:
    """Returns members expiring within the next `days` days."""
    today  = datetime.now().strftime('%Y-%m-%d')
    cutoff = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
    conn   = get_connection()
    rows   = conn.execute("""
        SELECT * FROM members
        WHERE status = 'active'
          AND expiry_date BETWEEN ? AND ?
        ORDER BY expiry_date ASC
    """, (today, cutoff)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Activity Log ──────────────────────────────────────────────

def log_activity(category: str, action: str,
                 detail: str = None, status: str = 'ok'):
    """
    Inserts one row into activity_log.
    category: 'pipeline', 'alert', 'member', 'payment', 'system'
    """
    now  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_connection()
    conn.execute("""
        INSERT INTO activity_log (timestamp, category, action, detail, status)
        VALUES (?, ?, ?, ?, ?)
    """, (now, category, action, detail, status))
    conn.commit()
    conn.close()


def get_recent_activity(limit: int = 30) -> list:
    """Returns the most recent activity_log entries."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM activity_log
        ORDER BY timestamp DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Analytics queries ─────────────────────────────────────────

def get_revenue_by_month() -> list:
    """
    Returns monthly revenue totals from subscriptions.
    Format: [{'month': '2026-03', 'revenue': 897.00}, ...]
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT strftime('%Y-%m', paid_date) AS month,
               SUM(amount) AS revenue
        FROM subscriptions
        WHERE status = 'paid'
        GROUP BY month
        ORDER BY month ASC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_member_growth() -> list:
    """
    Returns cumulative member count by join month.
    Format: [{'month': '2026-03', 'cumulative': 5}, ...]
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT strftime('%Y-%m', joined_date) AS month,
               COUNT(*) AS new_members
        FROM members
        GROUP BY month
        ORDER BY month ASC
    """).fetchall()
    conn.close()
    cumulative = 0
    result     = []
    for r in rows:
        cumulative += r['new_members']
        result.append({'month': r['month'], 'cumulative': cumulative})
    return result


def get_plan_distribution() -> dict:
    """Returns count of active members by plan type."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT plan, COUNT(*) AS count
        FROM members
        WHERE status = 'active'
        GROUP BY plan
    """).fetchall()
    conn.close()
    return {r['plan']: r['count'] for r in rows}


def get_member_stats() -> dict:
    """Returns high-level member counts for the home dashboard."""
    conn = get_connection()
    row = conn.execute("""
        SELECT
            SUM(CASE WHEN status = 'active'    THEN 1 ELSE 0 END) AS active,
            SUM(CASE WHEN status = 'expired'   THEN 1 ELSE 0 END) AS expired,
            SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled
        FROM members
    """).fetchone()
    conn.close()
    if row:
        return {k: (v or 0) for k, v in dict(row).items()}
    return {'active': 0, 'expired': 0, 'cancelled': 0}
