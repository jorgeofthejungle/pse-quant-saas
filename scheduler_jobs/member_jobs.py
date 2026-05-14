# scheduler_jobs/member_jobs.py — Member lifecycle jobs (expiry notifications)
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'discord'))


def run_expiry_notifications():
    """
    Daily job (9:00 AM PHT) — sends Discord alerts for subscriptions
    expiring in 7 days, 1 day, or today.

    Uses DISCORD_WEBHOOK_ALERTS channel so notifications go to the
    admin's alerts channel. Admin can then forward renewal links to
    members via Discord DM.
    """
    from publisher import WEBHOOKS, send_expiry_notification

    today = datetime.now().strftime('%Y-%m-%d')
    print(f"\n[expiry_notifications]  {today}")

    try:
        from dashboard.db_members import get_expiring_soon, log_activity
    except ImportError:
        try:
            from db_members import get_expiring_soon, log_activity
        except ImportError as e:
            print(f"  [expiry] db_members import failed: {e}")
            return

    alerts_url = WEBHOOKS.get('alerts', '')
    if not alerts_url:
        print("  [expiry] DISCORD_WEBHOOK_ALERTS not set — skipping.")
        return

    notified = 0
    for days_left in (7, 1, 0):
        expiring    = get_expiring_soon(days=days_left)
        target_date = (datetime.now() + timedelta(days=days_left)).strftime('%Y-%m-%d')
        on_day      = [m for m in expiring if m.get('expiry_date') == target_date]

        for member in on_day:
            try:
                send_expiry_notification(
                    webhook_url = alerts_url,
                    member_name = member['discord_name'],
                    expiry_date = member['expiry_date'],
                    days_left   = days_left,
                )
                log_activity(
                    'member', 'expiry_notification_sent',
                    f"{member['discord_name']} — {days_left}d remaining",
                )
                notified += 1
                print(f"  [expiry] Notified: {member['discord_name']} ({days_left}d)")
            except Exception as e:
                print(f"  [expiry] Failed for {member.get('discord_name', '?')}: {e}")

    print(f"  [expiry] {notified} notification(s) sent.")
