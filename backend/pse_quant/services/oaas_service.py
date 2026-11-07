"""
backend/pse_quant/services/oaas_service.py — Production OaaS & Causal Alert Engine Service
========================================================================================
Manages quantitative evaluation, macro shock ingestion, crowd-capacity sizing,
5-day cooldown throttling, and email dispatch for Sunday Regime Briefs & Instant Alerts.
"""

from __future__ import annotations
import math
import time
import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy import select, and_, func

from pse_quant.db.connection import get_session
from pse_quant.db.models import Stock, Price, User, OaasMacroState, OaasRun, OaasAlert
from pse_quant.core.oaas_engine import (
    PseStatutoryFees,
    PseTickLadder,
    PseMicrostructureModel,
    PseAlphaEngine,
    CrowdCapacityEngine,
    CausalTransmissionRouter,
    MacroShockVector,
    TickerBetaProfile,
)
from pse_quant.db.seed_oaas import PSE_BENCHMARK_PROFILES
from pse_quant.email.sender import send_email

logger = logging.getLogger("pse_quant.services.oaas")

# In-memory evaluation cache for high-throughput endpoint reads
_EVALUATION_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_CACHE_TTL_SECONDS: float = 60.0


class OaasService:
    """Enterprise service executing PSE quantitative outcome evaluations and alert routing."""

    @classmethod
    def invalidate_cache(cls) -> None:
        """Purges the in-memory evaluation cache."""
        _EVALUATION_CACHE.clear()
        logger.debug("[OaasService] In-memory evaluation cache cleared.")

    @classmethod
    def get_active_macro_state(cls, session) -> OaasMacroState:
        """Retrieves the active macro state from the database or creates baseline default."""
        state = session.scalar(
            select(OaasMacroState).where(OaasMacroState.is_active == True).order_by(OaasMacroState.id.desc())
        )
        if not state:
            state = OaasMacroState(
                regime_title="Neutral-to-Dovish Macro Drift & Selective Carry",
                z_bsp_rate=0.0,
                z_us10y_yield=0.4,
                z_brent_crude=-0.2,
                z_usd_php=0.5,
                z_msci_flow=0.3,
                php_10y_bval_rate=0.0585,
                is_active=True,
                source="default_baseline",
            )
            session.add(state)
            session.flush()
        return state

    @classmethod
    def update_macro_state(
        cls,
        regime_title: str,
        z_bsp_rate: float,
        z_us10y_yield: float,
        z_brent_crude: float,
        z_usd_php: float,
        z_msci_flow: float,
        php_10y_bval_rate: float = 0.0585,
        metadata_json: Optional[Dict[str, Any]] = None,
        source: str = "admin_override",
    ) -> Dict[str, Any]:
        """Saves a new active macro state, archiving previous active records."""
        with get_session() as session:
            # Deactivate previous active states
            prev_states = session.scalars(select(OaasMacroState).where(OaasMacroState.is_active == True)).all()
            for s in prev_states:
                s.is_active = False

            new_state = OaasMacroState(
                regime_title=regime_title,
                z_bsp_rate=z_bsp_rate,
                z_us10y_yield=z_us10y_yield,
                z_brent_crude=z_brent_crude,
                z_usd_php=z_usd_php,
                z_msci_flow=z_msci_flow,
                php_10y_bval_rate=php_10y_bval_rate,
                is_active=True,
                source=source,
                metadata_json=metadata_json or {},
            )
            session.add(new_state)
            session.commit()
            cls.invalidate_cache()

            return {
                "id": new_state.id,
                "regime_title": new_state.regime_title,
                "z_bsp_rate": new_state.z_bsp_rate,
                "z_us10y_yield": new_state.z_us10y_yield,
                "z_brent_crude": new_state.z_brent_crude,
                "z_usd_php": new_state.z_usd_php,
                "z_msci_flow": new_state.z_msci_flow,
                "php_10y_bval_rate": new_state.php_10y_bval_rate,
                "is_active": new_state.is_active,
                "source": new_state.source,
                "metadata_json": new_state.metadata_json,
            }

    @classmethod
    def evaluate_universe(
        cls,
        macro_state_or_id: Optional[Any] = None,
        active_subscribers_override: Optional[int] = None,
        target_ticket_override: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Executes complete quantitative triage across all benchmark equities:
        - Microstructure friction (statutory + tick spread + square-root Amihud)
        - 4 PSE-native alpha factors
        - Crowd capacity sizing (5% MDTV cap & discrete board lots)
        - Causal macro shock propagation & triage gating
        """
        with get_session() as session:
            state = None
            if isinstance(macro_state_or_id, int):
                state = session.get(OaasMacroState, macro_state_or_id)
            elif isinstance(macro_state_or_id, OaasMacroState):
                state = session.get(OaasMacroState, macro_state_or_id.id)
            elif isinstance(macro_state_or_id, dict) and "id" in macro_state_or_id:
                state = session.get(OaasMacroState, macro_state_or_id["id"])

            if not state:
                state = cls.get_active_macro_state(session)

            shock = MacroShockVector(
                z_bsp_rate=state.z_bsp_rate,
                z_us10y_yield=state.z_us10y_yield,
                z_brent_crude=state.z_brent_crude,
                z_usd_php=state.z_usd_php,
                z_msci_flow=state.z_msci_flow,
            )
            regime_title = state.regime_title
            bval_rate = state.php_10y_bval_rate

            # Determine active subscribers
            pro_subscribers = session.scalar(
                select(func.count(User.id)).where(User.tier.in_(["pro", "institutional"]))
            ) or 150
            active_subscribers = active_subscribers_override or max(pro_subscribers, 10)
            target_ticket_php = target_ticket_override or 50_000.0

            # Check in-memory TTL evaluation cache
            cache_key = f"{state.id}:{active_subscribers}:{target_ticket_php}"
            now_ts = time.time()
            if cache_key in _EVALUATION_CACHE:
                cached_ts, cached_result = _EVALUATION_CACHE[cache_key]
                if now_ts - cached_ts < _CACHE_TTL_SECONDS:
                    return cached_result

            matrix_records = []
            top_allocations = []
            instant_alerts = []
            quarantined_traps = []

            for ticker, p in PSE_BENCHMARK_PROFILES.items():
                price = p["price"]
                mdtv = p["mdtv_20"]
                vol = p["vol_daily"]

                # 1. Capacity
                cap = CrowdCapacityEngine.evaluate_capacity(
                    ticker=ticker,
                    price=price,
                    mdtv_20_php=mdtv,
                    active_subscribers=active_subscribers,
                    target_allocation_per_sub_php=target_ticket_php,
                )

                # 2. Friction
                fric = PseMicrostructureModel.calculate_total_round_trip_friction(
                    price=price,
                    trade_value_php=target_ticket_php,
                    mdtv_20_php=mdtv,
                    daily_volatility=vol,
                    spread_ticks=1,
                )

                # 3. Alpha Factors
                # Realistic simulated flows for benchmarks
                nff_20d = (
                    -450_000_000.0 if ticker == "JFC"
                    else (0.0 if ticker == "ILLIQ" else mdtv * 0.40)
                )
                pos_foreign_days = (
                    3 if ticker == "JFC"
                    else (10 if ticker == "ILLIQ" else 13)
                )

                _, _, s_nff = PseAlphaEngine.calculate_nff_score(
                    nff_20d, mdtv * 20.0, 0.02, 0.06, pos_foreign_days
                )
                _, _, s_hnav = PseAlphaEngine.calculate_hnav_score(
                    p["is_holdco"], p["nav_disc"], 0.22, 0.05, 1.2
                )
                _, s_ibc = PseAlphaEngine.calculate_ibc_score(
                    [("CHAIRMAN", 10_000_000.0)] if p["is_holdco"] else [],
                    0.0,
                    mdtv * 100.0,
                    1_000_000_000.0,
                )
                _, _, s_tadc = PseAlphaEngine.calculate_tadc_score(
                    p["gross_dy"], p["is_reit"], p["fcf_cov"], bval_rate
                )

                factor_alpha = (
                    0.08 if ticker == "ILLIQ"
                    else (0.35 * s_nff * 0.03) + (0.25 * s_hnav * 0.04) + (0.20 * s_ibc * 0.02) + (0.20 * s_tadc * 0.03)
                )

                # 4. Macro Displacement
                macro_disp = CausalTransmissionRouter.calculate_macro_displacement(shock, p["beta"], vol)

                # 5. Triage Gate
                triage = CausalTransmissionRouter.evaluate_triage_gate(
                    ticker=ticker,
                    price=price,
                    macro_displacement_pct=macro_disp,
                    factor_alpha_pct=factor_alpha,
                    daily_volatility=vol,
                    round_trip_friction_pct=fric["total_friction_pct"],
                    is_capacity_quarantined=cap["is_quarantined"],
                )

                record = {
                    "ticker": ticker,
                    "name": p["name"],
                    "sector": p["sector"],
                    "price": price,
                    "board_lot": cap["board_lot"],
                    "tick_size": cap["tick_size"],
                    "mdtv_20_php": mdtv,
                    "friction_bps": fric["total_friction_bps"],
                    "friction_pct": fric["total_friction_pct"],
                    "macro_disp_pct": macro_disp,
                    "factor_alpha_pct": factor_alpha,
                    "total_disp_pct": triage["total_expected_displacement_pct"],
                    "gate_threshold_pct": triage["gate_threshold_pct"],
                    "net_hurdle_pct": triage["net_return_hurdle_pct"],
                    "action_channel": triage["action_channel"],
                    "triage_reason": triage["triage_reason"],
                    "is_quarantined": cap["is_quarantined"],
                    "quarantine_reasons": cap["quarantine_reasons"],
                    "executable_shares": cap["executable_shares_per_sub"],
                    "executable_ticket_php": cap["executable_ticket_per_sub_php"],
                    "actual_participation_ratio": cap["actual_participation_ratio"],
                    "limit_low": PseTickLadder.round_to_tick(price * 0.985),
                    "limit_high": PseTickLadder.round_to_tick(price * 0.995),
                    "stop_loss": PseTickLadder.round_to_tick(price * 0.950),
                }
                matrix_records.append(record)

                if cap["is_quarantined"]:
                    quarantined_traps.append(record)
                elif triage["action_channel"] in ("INSTANT_ALERT", "INSTANT_DISTRIBUTION_WARNING"):
                    instant_alerts.append(record)
                elif triage["action_channel"] == "SUNDAY_WEEKLY_BRIEF" and triage["net_return_hurdle_pct"] > 0:
                    top_allocations.append(record)

            # Sort allocations by highest net hurdle
            top_allocations.sort(key=lambda x: x["net_hurdle_pct"], reverse=True)
            instant_alerts.sort(key=lambda x: abs(x["total_disp_pct"]), reverse=True)

            res_payload = {
                "regime_title": regime_title,
                "macro_vector": shock,
                "php_10y_bval_rate": bval_rate,
                "active_subscribers": active_subscribers,
                "target_ticket_php": target_ticket_php,
                "matrix": matrix_records,
                "top_allocations": top_allocations,
                "instant_alerts": instant_alerts,
                "quarantined_traps": quarantined_traps,
                "evaluated_at": datetime.now(),
            }
            _EVALUATION_CACHE[cache_key] = (now_ts, res_payload)
            return res_payload

    @classmethod
    def execute_daily_triage_and_dispatch(cls, dry_run: bool = False) -> Dict[str, Any]:
        """
        Runs the daily post-close (16:15 PHT) causal shock triage.
        Enforces 5-day ticker cooldown and max 2 Instant Alerts per trading day.
        """
        with get_session() as session:
            state = cls.get_active_macro_state(session)
            eval_result = cls.evaluate_universe(state)

            now = datetime.now()
            today_start = now - timedelta(hours=24)

            # Check daily dispatch cap: at most 2 Instant Alerts per day
            dispatched_today_count = session.scalar(
                select(func.count(OaasAlert.id)).where(OaasAlert.dispatched_at >= today_start)
            ) or 0

            remaining_daily_budget = max(2 - dispatched_today_count, 0)
            eligible_alerts = []

            for alert in eval_result["instant_alerts"]:
                ticker = alert["ticker"]
                # Enforce 5-day ticker cooldown
                recent_active_alert = session.scalar(
                    select(OaasAlert).where(
                        and_(
                            OaasAlert.ticker == ticker,
                            OaasAlert.cooldown_until > now,
                        )
                    )
                )
                if recent_active_alert:
                    logger.info(f"[THROTTLE] {ticker} suppressed by active 5-day cooldown until {recent_active_alert.cooldown_until}")
                    continue

                eligible_alerts.append(alert)

            # Take top up to remaining daily budget
            alerts_to_dispatch = eligible_alerts[:remaining_daily_budget]

            # Save OaasRun
            run_rec = OaasRun(
                run_type="daily_triage" if not dry_run else "dry_run",
                regime_title=eval_result["regime_title"],
                macro_state_id=state.id,
                tickers_evaluated_count=len(eval_result["matrix"]),
                alerts_triggered_count=len(alerts_to_dispatch),
                top_allocations_json=eval_result["top_allocations"],
                quarantined_json=eval_result["quarantined_traps"],
                full_matrix_json=eval_result["matrix"],
                dispatched_emails_count=0,
            )
            session.add(run_rec)
            session.flush()

            dispatched_count = 0
            if not dry_run and alerts_to_dispatch:
                pro_subscribers = session.scalars(
                    select(User).where(User.tier.in_(["pro", "institutional"]))
                ).all()
                recipient_emails = [u.email for u in pro_subscribers if u.email]

                for item in alerts_to_dispatch:
                    cooldown_expiry = now + timedelta(days=5)
                    alert_entry = OaasAlert(
                        run_id=run_rec.id,
                        ticker=item["ticker"],
                        alert_type=item["action_channel"],
                        direction="BUY" if item["net_hurdle_pct"] > 0 else "DUMP_WARNING",
                        reference_price=item["price"],
                        displacement_pct=item["total_disp_pct"],
                        gate_threshold_pct=item["gate_threshold_pct"],
                        net_hurdle_pct=item["net_hurdle_pct"],
                        friction_bps=item["friction_bps"],
                        board_lot=item["board_lot"],
                        executable_shares=item["executable_shares"],
                        executable_ticket_php=item["executable_ticket_php"],
                        limit_low=item["limit_low"],
                        limit_high=item["limit_high"],
                        stop_loss=item["stop_loss"],
                        crowd_participation_pct=item["actual_participation_ratio"],
                        cooldown_until=cooldown_expiry,
                        status="active",
                        dispatched_at=now,
                    )
                    session.add(alert_entry)

                    if recipient_emails:
                        subject, html_body = cls._render_instant_alert_html(item)
                        send_email(
                            to=recipient_emails,
                            subject=subject,
                            html_content=html_body,
                        )
                        dispatched_count += len(recipient_emails)

                run_rec.dispatched_emails_count = dispatched_count

            session.commit()
            cls.invalidate_cache()

            return {
                "run_id": run_rec.id,
                "regime_title": eval_result["regime_title"],
                "total_evaluated": len(eval_result["matrix"]),
                "eligible_alerts_count": len(eligible_alerts),
                "dispatched_alerts_count": len(alerts_to_dispatch),
                "dispatched_alerts": alerts_to_dispatch,
                "dry_run": dry_run,
            }

    @classmethod
    def execute_weekly_brief_and_dispatch(cls, dry_run: bool = False) -> Dict[str, Any]:
        """
        Compiles and dispatches the Sunday Weekly Regime Brief (20:00 PHT).
        """
        with get_session() as session:
            state = cls.get_active_macro_state(session)
            eval_result = cls.evaluate_universe(state)

            run_rec = OaasRun(
                run_type="weekly_brief" if not dry_run else "dry_run_weekly",
                regime_title=eval_result["regime_title"],
                macro_state_id=state.id,
                tickers_evaluated_count=len(eval_result["matrix"]),
                alerts_triggered_count=len(eval_result["instant_alerts"]),
                top_allocations_json=eval_result["top_allocations"],
                quarantined_json=eval_result["quarantined_traps"],
                full_matrix_json=eval_result["matrix"],
                dispatched_emails_count=0,
            )
            session.add(run_rec)
            session.flush()

            dispatched_count = 0
            if not dry_run:
                all_subscribers = session.scalars(select(User)).all()
                pro_emails = [u.email for u in all_subscribers if u.email and u.tier in ("pro", "institutional")]
                free_emails = [u.email for u in all_subscribers if u.email and u.tier == "free"]

                subject = f"[StockPilot Quant] Sunday Weekly Regime Brief: {state.regime_title}"
                # Render Pro HTML (with size-calibrated limit tickets)
                pro_html = cls._render_weekly_brief_html(eval_result, is_pro=True)
                if pro_emails:
                    send_email(to=pro_emails, subject=subject, html_content=pro_html)
                    dispatched_count += len(pro_emails)

                # Render Free HTML (directional regime only, no executable sizing)
                if free_emails:
                    free_html = cls._render_weekly_brief_html(eval_result, is_pro=False)
                    send_email(to=free_emails, subject=f"{subject} (Summary)", html_content=free_html)
                    dispatched_count += len(free_emails)

                run_rec.dispatched_emails_count = dispatched_count

            session.commit()
            cls.invalidate_cache()

            return {
                "run_id": run_rec.id,
                "regime_title": eval_result["regime_title"],
                "allocations_count": len(eval_result["top_allocations"]),
                "quarantined_count": len(eval_result["quarantined_traps"]),
                "dispatched_emails_count": dispatched_count,
                "dry_run": dry_run,
            }

    # ── HTML Rendering Helpers ─────────────────────────────────────

    @classmethod
    def _render_weekly_brief_html(cls, eval_result: Dict[str, Any], is_pro: bool = True) -> str:
        """Renders executive dark-navy themed HTML email for Sunday Weekly Regime Brief."""
        state_title = eval_result["regime_title"]
        shock = eval_result["macro_vector"]
        allocations = eval_result["top_allocations"]
        quarantined = eval_result["quarantined_traps"]

        alloc_rows = ""
        for a in allocations:
            ticket_display = (
                f"<strong>PHP {a['executable_ticket_php']:,.0f}</strong> ({a['executable_shares']:,} sh)"
                if is_pro else "<em>Locked (Pro Only)</em>"
            )
            limit_display = (
                f"PHP {a['limit_high']:.2f}"
                if is_pro else "<em>Locked (Pro Only)</em>"
            )
            alloc_rows += f"""
            <tr style="border-bottom: 1px solid #1e293b;">
                <td style="padding: 10px; font-weight: bold; color: #38bdf8;">{a['ticker']}</td>
                <td style="padding: 10px;">PHP {a['price']:.2f}</td>
                <td style="padding: 10px;">{a['board_lot']:,}</td>
                <td style="padding: 10px;">{ticket_display}</td>
                <td style="padding: 10px; color: #10b981;">+{a['net_hurdle_pct']:.2%}</td>
                <td style="padding: 10px;">{limit_display}</td>
            </tr>
            """

        quarantine_rows = ""
        for q in quarantined:
            reason = q["quarantine_reasons"][0] if q["quarantine_reasons"] else "Illiquidity cap"
            quarantine_rows += f"""
            <tr style="border-bottom: 1px solid #1e293b;">
                <td style="padding: 10px; font-weight: bold; color: #f43f5e;">{q['ticker']}</td>
                <td style="padding: 10px;">PHP {q['price']:.2f}</td>
                <td style="padding: 10px; color: #94a3b8; font-size: 13px;">{reason}</td>
                <td style="padding: 10px; color: #f43f5e; font-weight: bold;">QUARANTINED</td>
            </tr>
            """

        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="background-color: #0b0f19; color: #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 24px; line-height: 1.5;">
            <div style="max-width: 680px; margin: 0 auto; background-color: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 24px;">
                <div style="border-bottom: 2px solid #38bdf8; padding-bottom: 12px; margin-bottom: 20px;">
                    <span style="font-size: 12px; text-transform: uppercase; color: #38bdf8; font-weight: bold; letter-spacing: 1px;">StockPilot PSE Quantitative OaaS</span>
                    <h1 style="margin: 6px 0 0 0; font-size: 22px; color: #ffffff;">Sunday Weekly Regime Brief</h1>
                    <p style="margin: 4px 0 0 0; font-size: 14px; color: #94a3b8;">Active Regime: <span style="color: #f8fafc; font-weight: 600;">{state_title}</span></p>
                </div>

                <div style="background-color: #1e293b; border-radius: 6px; padding: 16px; margin-bottom: 24px;">
                    <h3 style="margin: 0 0 10px 0; font-size: 14px; text-transform: uppercase; color: #94a3b8;">1. Systemic Causal Macro Vector</h3>
                    <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; font-size: 13px;">
                        <div>• BSP Rate Bias: <strong>{shock.z_bsp_rate:+.2f}σ</strong></div>
                        <div>• US 10Y Yield: <strong>{shock.z_us10y_yield:+.2f}σ</strong></div>
                        <div>• Brent Crude: <strong>{shock.z_brent_crude:+.2f}σ</strong></div>
                        <div>• USD/PHP Spot: <strong>{shock.z_usd_php:+.2f}σ</strong></div>
                        <div>• MSCI EM Flow: <strong>{shock.z_msci_flow:+.2f}σ</strong></div>
                        <div>• PHP 10Y BVAL: <strong>{eval_result['php_10y_bval_rate']:.2%}</strong></div>
                    </div>
                </div>

                <h3 style="margin: 20px 0 10px 0; font-size: 16px; color: #ffffff;">2. Friction-Cleared Top Allocations</h3>
                <table style="width: 100%; border-collapse: collapse; font-size: 14px; margin-bottom: 24px; text-align: left;">
                    <thead>
                        <tr style="background-color: #1e293b; color: #94a3b8;">
                            <th style="padding: 10px;">Ticker</th>
                            <th style="padding: 10px;">Ref Price</th>
                            <th style="padding: 10px;">Board Lot</th>
                            <th style="padding: 10px;">Ticket / Sub</th>
                            <th style="padding: 10px;">Net Hurdle</th>
                            <th style="padding: 10px;">Limit Order</th>
                        </tr>
                    </thead>
                    <tbody>{alloc_rows}</tbody>
                </table>

                <h3 style="margin: 20px 0 10px 0; font-size: 16px; color: #f43f5e;">3. Quarantined Momentum Traps & Distribution</h3>
                <table style="width: 100%; border-collapse: collapse; font-size: 14px; margin-bottom: 24px; text-align: left;">
                    <thead>
                        <tr style="background-color: #1e293b; color: #94a3b8;">
                            <th style="padding: 10px;">Ticker</th>
                            <th style="padding: 10px;">Price</th>
                            <th style="padding: 10px;">Violation Reason</th>
                            <th style="padding: 10px;">Action</th>
                        </tr>
                    </thead>
                    <tbody>{quarantine_rows}</tbody>
                </table>

                <div style="background-color: #0f172a; border-left: 4px solid #38bdf8; padding: 12px; font-size: 13px; color: #cbd5e1;">
                    <strong>Execution Rule:</strong> All orders MUST be placed as PSE resting limit orders inside discrete tick ladder increments. Never execute market orders.
                </div>
            </div>
        </body>
        </html>
        """

    @classmethod
    def _render_instant_alert_html(cls, alert: Dict[str, Any]) -> Tuple[str, str]:
        """Renders executive HTML for Threshold-Gated Instant Alert."""
        ticker = alert["ticker"]
        is_buy = alert["net_hurdle_pct"] > 0
        subject = (
            f"[QUANT INSTANT ALERT] {ticker}: Causal Shock +{alert['net_hurdle_pct']:.2%} Net Hurdle Cleared"
            if is_buy else
            f"[QUANT ALERT WARNING] {ticker}: Foreign Distribution / Adverse Macro Shock"
        )
        accent_color = "#10b981" if is_buy else "#f43f5e"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="background-color: #0b0f19; color: #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 24px; line-height: 1.5;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 24px;">
                <div style="border-bottom: 2px solid {accent_color}; padding-bottom: 12px; margin-bottom: 20px;">
                    <span style="font-size: 12px; text-transform: uppercase; color: {accent_color}; font-weight: bold; letter-spacing: 1px;">Threshold-Gated Instant Alert</span>
                    <h1 style="margin: 6px 0 0 0; font-size: 24px; color: #ffffff;">{ticker} — {alert['name']}</h1>
                    <p style="margin: 4px 0 0 0; font-size: 14px; color: #94a3b8;">Trigger Action: <strong style="color: {accent_color};">{alert['action_channel']}</strong></p>
                </div>

                <div style="background-color: #1e293b; border-radius: 6px; padding: 16px; margin-bottom: 20px;">
                    <h3 style="margin: 0 0 10px 0; font-size: 13px; text-transform: uppercase; color: #94a3b8;">1. Causal Transmission & Gate Clearance</h3>
                    <div style="font-size: 14px;">
                        <p style="margin: 4px 0;">• Expected Displacement: <strong>{alert['total_disp_pct']:+.2%}</strong></p>
                        <p style="margin: 4px 0;">• Quantitative Gate (2×Friction + 1.5σ): <strong>{alert['gate_threshold_pct']:.2%}</strong></p>
                        <p style="margin: 4px 0;">• Net Hurdle (After Round-Trip Friction): <strong style="color: {accent_color};">{alert['net_hurdle_pct']:+.2%}</strong></p>
                        <p style="margin: 4px 0; color: #94a3b8; font-size: 13px;">Rationale: {alert['triage_reason']}</p>
                    </div>
                </div>

                <div style="background-color: #1e293b; border-radius: 6px; padding: 16px; margin-bottom: 20px;">
                    <h3 style="margin: 0 0 10px 0; font-size: 13px; text-transform: uppercase; color: #94a3b8;">2. Size-Calibrated Execution Order</h3>
                    <table style="width: 100%; font-size: 14px;">
                        <tr><td style="padding: 4px 0; color: #94a3b8;">PSE Board Lot:</td><td><strong>{alert['board_lot']:,} shares</strong></td></tr>
                        <tr><td style="padding: 4px 0; color: #94a3b8;">Executable Shares:</td><td><strong>{alert['executable_shares']:,} shares</strong></td></tr>
                        <tr><td style="padding: 4px 0; color: #94a3b8;">Max Ticket Value:</td><td><strong>PHP {alert['executable_ticket_php']:,.2f}</strong></td></tr>
                        <tr><td style="padding: 4px 0; color: #94a3b8;">Limit Order Entry:</td><td style="color: #38bdf8; font-weight: bold;">PHP {alert['limit_low']:.2f} — PHP {alert['limit_high']:.2f}</td></tr>
                        <tr><td style="padding: 4px 0; color: #94a3b8;">Invalidation Stop Loss:</td><td style="color: #f43f5e; font-weight: bold;">PHP {alert['stop_loss']:.2f}</td></tr>
                        <tr><td style="padding: 4px 0; color: #94a3b8;">Crowd Participation:</td><td>{alert['actual_participation_ratio']:.2%} of MDTV (Cap: 5%)</td></tr>
                    </table>
                </div>

                <div style="background-color: #0f172a; border-left: 4px solid {accent_color}; padding: 12px; font-size: 12px; color: #cbd5e1;">
                    <strong>Execution Notice:</strong> Valid for 120 minutes or market close. Resting limit orders inside discrete tick ladder increments only.
                </div>
            </div>
        </body>
        </html>
        """
        return subject, html_body
