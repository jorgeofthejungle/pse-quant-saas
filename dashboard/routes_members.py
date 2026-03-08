# ============================================================
# routes_members.py — Member Management
# PSE Quant SaaS — Dashboard
# ============================================================

import sys
from datetime import datetime
from pathlib import Path
from flask import (Blueprint, render_template, request,
                   redirect, url_for, flash, jsonify)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dashboard.db_members import (
    get_all_members, get_member, add_member, update_member,
    extend_member, cancel_member, record_payment,
    get_member_subscriptions, get_expiring_soon,
    expire_overdue_members, get_member_stats, bulk_cancel_inactive,
)

members_bp = Blueprint('members', __name__)


@members_bp.route('/')
def index():
    expire_overdue_members()
    status_filter = request.args.get('status')          # 'active'|'expired'|None
    members       = get_all_members(status_filter)
    expired_count = len(get_all_members('expired'))
    expiring_soon = get_expiring_soon(days=7)
    stats         = get_member_stats()

    return render_template('members.html',
                           members=members,
                           status_filter=status_filter or 'all',
                           expired_count=expired_count,
                           expiring_soon=expiring_soon,
                           stats=stats)


@members_bp.route('/add', methods=['POST'])
def add():
    discord_name = request.form.get('discord_name', '').strip()
    plan         = request.form.get('plan', 'monthly')
    discord_id   = request.form.get('discord_id', '').strip() or None
    email        = request.form.get('email', '').strip() or None
    notes        = request.form.get('notes', '').strip() or None

    if not discord_name:
        flash('Discord name is required.', 'error')
        return redirect(url_for('members.index'))

    member_id = add_member(discord_name, plan, discord_id, email, notes)
    flash(f'Member {discord_name} added successfully.', 'success')
    return redirect(url_for('members.detail', member_id=member_id))


@members_bp.route('/<int:member_id>')
def detail(member_id: int):
    expire_overdue_members()
    member = get_member(member_id)
    if not member:
        flash('Member not found.', 'error')
        return redirect(url_for('members.index'))

    subscriptions = get_member_subscriptions(member_id)
    today         = datetime.now().strftime('%Y-%m-%d')
    days_left     = None
    if member.get('expiry_date'):
        try:
            delta     = (datetime.strptime(member['expiry_date'], '%Y-%m-%d')
                         - datetime.now())
            days_left = delta.days
        except Exception:
            pass

    return render_template('member_detail.html',
                           member=member,
                           subscriptions=subscriptions,
                           today=today,
                           days_left=days_left)


@members_bp.route('/<int:member_id>/edit', methods=['POST'])
def edit(member_id: int):
    update_member(
        member_id,
        discord_name = request.form.get('discord_name') or None,
        discord_id   = request.form.get('discord_id')   or None,
        email        = request.form.get('email')         or None,
        plan         = request.form.get('plan')          or None,
        notes        = request.form.get('notes')         or None,
    )
    flash('Member updated.', 'success')
    return redirect(url_for('members.detail', member_id=member_id))


@members_bp.route('/<int:member_id>/extend', methods=['POST'])
def extend(member_id: int):
    plan = request.form.get('plan', 'monthly')
    days = 365 if plan == 'annual' else 30
    extend_member(member_id, days, source='manual_extend')
    flash(f'Subscription extended by {days} days.', 'success')
    return redirect(url_for('members.detail', member_id=member_id))


@members_bp.route('/<int:member_id>/mark-paid', methods=['POST'])
def mark_paid(member_id: int):
    """Records a manual payment and extends the subscription."""
    plan   = request.form.get('plan', 'monthly')
    method = request.form.get('method', 'manual')
    amount = request.form.get('amount', '')

    try:
        amount = float(amount)
    except (ValueError, TypeError):
        flash('Invalid payment amount.', 'error')
        return redirect(url_for('members.detail', member_id=member_id))

    record_payment(member_id, amount, plan, payment_method=method)
    flash(f'Payment of PHP {amount:.2f} recorded. Subscription extended.', 'success')
    return redirect(url_for('members.detail', member_id=member_id))


@members_bp.route('/<int:member_id>/cancel', methods=['POST'])
def cancel(member_id: int):
    cancel_member(member_id)
    flash('Member marked as cancelled.', 'success')
    return redirect(url_for('members.index'))


@members_bp.route('/bulk-cancel', methods=['POST'])
def bulk_cancel():
    """Marks all expired and cancelled members as cancelled (archive/clean up)."""
    count = bulk_cancel_inactive()
    flash(f'{count} non-active member(s) archived as cancelled.', 'success')
    return redirect(url_for('members.index'))


@members_bp.route('/expired')
def expired():
    """JSON: list of expired members (for quick review)."""
    expire_overdue_members()
    members = get_all_members('expired')
    return jsonify(members)
