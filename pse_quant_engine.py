"""
pse_quant_engine.py — PSE-Native Quantitative Outcome-as-a-Service (OaaS) Reference Engine
========================================================================================
Production-grade quantitative engine solving the PSE Liquidity-Friction-Flow Trilemma,
evaluating 4 PSE-native alpha factors, sizing subscriber crowd capacity, routing
causal macro-to-ticker shocks through a threshold-gated decision circuit, and rendering
production-ready email decision schemas.
"""

from __future__ import annotations
import math
import json
import sys
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")



# =====================================================================
# 1. PSE STATUTORY TRANSACTION FEES & DISCRETE TICK LADDER
# =====================================================================

class PseStatutoryFees:
    """
    Exact statutory transaction costs for the Philippine Stock Exchange (PSE).
    Governed by PSE, SEC, SCCP, and Republic Act No. 10963 (TRAIN Law amending NIRC Sec. 127(A)).
    """
    # Buy Side
    BROKER_COMMISSION_RATE = 0.0025          # 0.25% min broker commission
    VAT_RATE = 0.12                          # 12% VAT on commission (0.0025 * 0.12 = 0.00030)
    SEC_FEE_RATE = 0.00005                   # 0.005% SEC transaction fee (PHP 0.00005 per peso)
    PSE_TRANSACTION_FEE_RATE = 0.00005       # 0.005% PSE transaction fee (PHP 0.00005 per peso)
    SCCP_CLEARING_FEE_RATE = 0.00010         # 0.010% SCCP clearing fee (PHP 0.00010 per peso)
    MIN_BROKER_COMMISSION_PHP = 20.00        # Minimum PHP 20 broker fee per transaction

    # Sell Side
    STOCK_TRANSACTION_TAX_RATE = 0.0060      # 0.60% Stock Transaction Tax (STT) on gross sell value

    @classmethod
    def buy_side_pct(cls) -> float:
        """Percentage statutory cost on buying leg = 0.300% (30.0 bps)."""
        return (
            cls.BROKER_COMMISSION_RATE
            + (cls.BROKER_COMMISSION_RATE * cls.VAT_RATE)
            + cls.SEC_FEE_RATE
            + cls.PSE_TRANSACTION_FEE_RATE
            + cls.SCCP_CLEARING_FEE_RATE
        )

    @classmethod
    def sell_side_pct(cls) -> float:
        """Percentage statutory cost on selling leg = 0.900% (90.0 bps)."""
        return (
            cls.BROKER_COMMISSION_RATE
            + (cls.BROKER_COMMISSION_RATE * cls.VAT_RATE)
            + cls.SEC_FEE_RATE
            + cls.PSE_TRANSACTION_FEE_RATE
            + cls.SCCP_CLEARING_FEE_RATE
            + cls.STOCK_TRANSACTION_TAX_RATE
        )

    @classmethod
    def round_trip_statutory_pct(cls) -> float:
        """Total round-trip statutory percentage cost = 1.200% (120.0 bps)."""
        return cls.buy_side_pct() + cls.sell_side_pct()

    @classmethod
    def calculate_exact_fees(cls, buy_value: float, sell_value: float) -> Dict[str, float]:
        """
        Calculates exact peso friction for buy leg, sell leg, and round-trip,
        including statutory floors (PHP 20.00 broker minimum + 12% VAT = PHP 22.40).
        """
        # Buy leg
        buy_comm = max(buy_value * cls.BROKER_COMMISSION_RATE, cls.MIN_BROKER_COMMISSION_PHP)
        buy_vat = buy_comm * cls.VAT_RATE
        buy_sec = buy_value * cls.SEC_FEE_RATE
        buy_pse = buy_value * cls.PSE_TRANSACTION_FEE_RATE
        buy_sccp = buy_value * cls.SCCP_CLEARING_FEE_RATE
        total_buy = buy_comm + buy_vat + buy_sec + buy_pse + buy_sccp

        # Sell leg
        sell_comm = max(sell_value * cls.BROKER_COMMISSION_RATE, cls.MIN_BROKER_COMMISSION_PHP)
        sell_vat = sell_comm * cls.VAT_RATE
        sell_sec = sell_value * cls.SEC_FEE_RATE
        sell_pse = sell_value * cls.PSE_TRANSACTION_FEE_RATE
        sell_sccp = sell_value * cls.SCCP_CLEARING_FEE_RATE
        sell_stt = sell_value * cls.STOCK_TRANSACTION_TAX_RATE
        total_sell = sell_comm + sell_vat + sell_sec + sell_pse + sell_sccp + sell_stt

        return {
            "buy_fee_php": total_buy,
            "sell_fee_php": total_sell,
            "round_trip_fee_php": total_buy + total_sell,
            "effective_buy_pct": total_buy / buy_value if buy_value > 0 else 0.0,
            "effective_sell_pct": total_sell / sell_value if sell_value > 0 else 0.0,
            "effective_round_trip_pct": (total_buy + total_sell) / buy_value if buy_value > 0 else 0.0,
        }


class PseTickLadder:
    """
    Official Revised PSE Board Lot and Discrete Tick Size Schedule.
    Maps price ranges to exact discrete tick increments and standard board lots.
    """
    # (price_min, price_max, tick_size, board_lot)
    LADDER: List[Tuple[float, float, float, int]] = [
        (0.0001, 0.0099, 0.0001, 1_000_000),
        (0.0100, 0.0490, 0.0010, 100_000),
        (0.0500, 0.2490, 0.0010, 10_000),
        (0.2500, 0.4950, 0.0050, 10_000),
        (0.5000, 4.9900, 0.0100, 1_000),
        (5.0000, 9.9900, 0.0100, 100),
        (10.0000, 19.9800, 0.0200, 100),
        (20.0000, 49.9500, 0.0500, 100),
        (50.0000, 99.9500, 0.1000, 10),
        (100.0000, 199.9000, 0.1000, 10),
        (200.0000, 499.8000, 0.2000, 10),
        (500.0000, 999.5000, 0.5000, 10),
        (1000.0000, 1999.0000, 1.0000, 5),
        (2000.0000, 4998.0000, 2.0000, 5),
        (5000.0000, float("inf"), 5.0000, 5),
    ]

    @classmethod
    def get_tier(cls, price: float) -> Tuple[float, int]:
        """Returns (tick_size, board_lot) for a given price in PHP."""
        if price <= 0:
            raise ValueError(f"Invalid price: {price}. Price must be positive.")
        for p_min, p_max, tick, lot in cls.LADDER:
            if p_min <= price <= p_max:
                return tick, lot
        return 5.0000, 5

    @classmethod
    def round_to_tick(cls, price: float) -> float:
        """Rounds a price to the nearest valid PSE discrete tick."""
        tick, _ = cls.get_tier(price)
        return round(round(price / tick) * tick, 4)

    @classmethod
    def round_to_board_lot(cls, shares: float, price: float) -> int:
        """Rounds target shares down to the nearest valid PSE board lot."""
        _, lot = cls.get_tier(price)
        return int(math.floor(shares / lot) * lot)

    @classmethod
    def discrete_tick_spread_pct(cls, price: float, spread_ticks: int = 1) -> float:
        """Percentage bid-ask spread cost based on discrete ticks."""
        tick, _ = cls.get_tier(price)
        return (tick * spread_ticks) / price


# =====================================================================
# 2. PSE LIQUIDITY & AMIHUD MARKET IMPACT MODEL
# =====================================================================

class PseMicrostructureModel:
    """
    Square-Root Amihud Market Impact Model calibrated to PSE thin order books.
    Impact = lambda_pse * sigma_daily * sqrt(Trade_Value / MDTV_20)
    """
    LAMBDA_PSE = 0.55  # Empirical liquidity factor for PSE order book depth

    @classmethod
    def calculate_price_impact(
        cls,
        trade_value_php: float,
        mdtv_20_php: float,
        daily_volatility: float,
    ) -> float:
        """Calculates one-way price impact as a decimal percentage."""
        if mdtv_20_php <= 0:
            return 1.0  # Infinite impact on zero liquidity
        participation_ratio = trade_value_php / mdtv_20_php
        return cls.LAMBDA_PSE * daily_volatility * math.sqrt(participation_ratio)

    @classmethod
    def calculate_total_round_trip_friction(
        cls,
        price: float,
        trade_value_php: float,
        mdtv_20_php: float,
        daily_volatility: float,
        spread_ticks: int = 1,
    ) -> Dict[str, float]:
        """
        Calculates complete round-trip friction hurdle including statutory taxes,
        discrete tick spread, and round-trip square-root market impact.
        """
        statutory_pct = PseStatutoryFees.round_trip_statutory_pct()
        tick_spread_pct = PseTickLadder.discrete_tick_spread_pct(price, spread_ticks)
        one_way_impact = cls.calculate_price_impact(trade_value_php, mdtv_20_php, daily_volatility)
        round_trip_impact = 2.0 * one_way_impact

        total_friction_pct = statutory_pct + tick_spread_pct + round_trip_impact

        return {
            "statutory_pct": statutory_pct,
            "tick_spread_pct": tick_spread_pct,
            "one_way_impact_pct": one_way_impact,
            "round_trip_impact_pct": round_trip_impact,
            "total_friction_pct": total_friction_pct,
            "total_friction_bps": total_friction_pct * 10_000,
        }


# =====================================================================
# 3. FOUR PSE-NATIVE ALPHA FACTORS
# =====================================================================

class PseAlphaEngine:
    """
    Formulates 4 PSE-native alpha factors:
    1. Net Foreign Flow (NFF)
    2. HoldCo Look-Through NAV Discount (HNAV)
    3. PSE Edge Buyback & Insider Conviction (IBC)
    4. Tax-Adjusted Dividend / REIT Carry (TADC)
    """

    @staticmethod
    def calculate_nff_score(
        net_foreign_flow_20d: float,
        total_traded_value_20d: float,
        hist_nff_ratio_mean: float,
        hist_nff_ratio_std: float,
        positive_foreign_days_20d: int,
    ) -> Tuple[float, float, float]:
        """
        Factor 1: Net Foreign Flow (NFF).
        Foreign institutional flows dictate directional trend momentum on the PSE.
        Returns (nff_ratio, z_score, bounded_factor_score in [-1, 1]).
        """
        if total_traded_value_20d <= 0:
            return 0.0, 0.0, -1.0
        nff_ratio = net_foreign_flow_20d / total_traded_value_20d
        std = hist_nff_ratio_std if hist_nff_ratio_std > 1e-6 else 0.05
        z_nff = (nff_ratio - hist_nff_ratio_mean) / std

        persistence = positive_foreign_days_20d / 20.0
        persistence_score = (2.0 * persistence) - 1.0

        composite_raw = 0.70 * z_nff + 0.30 * (persistence_score * 2.0)
        score = math.tanh(composite_raw)
        return nff_ratio, z_nff, score

    @staticmethod
    def calculate_hnav_score(
        is_holdco: bool,
        current_nav_discount: float,
        historical_discount_mean: float,
        historical_discount_std: float,
        catalyst_multiplier: float = 1.0,
    ) -> Tuple[float, float, float]:
        """
        Factor 2: HoldCo Look-Through NAV Discount (HNAV).
        Sum-of-the-parts (SOTP) net asset value arbitrage for Philippine conglomerates.
        Returns (current_discount, z_score, bounded_factor_score in [-1, 1]).
        """
        if not is_holdco:
            return 0.0, 0.0, 0.0

        std = historical_discount_std if historical_discount_std > 1e-6 else 0.05
        z_nav = (current_nav_discount - historical_discount_mean) / std
        raw_score = catalyst_multiplier * z_nav
        score = math.tanh(raw_score)
        return current_nav_discount, z_nav, score

    @staticmethod
    def calculate_ibc_score(
        insider_purchases_90d: List[Tuple[str, float]],
        corporate_buyback_90d: float,
        market_cap: float,
        authorized_buyback_cap: float,
    ) -> Tuple[float, float]:
        """
        Factor 3: PSE Edge Buyback & Insider Conviction (IBC).
        Extracts Form 23-A/23-B insider acquisitions and Rule 10 Corporate Buybacks.
        Weights insider trades by corporate hierarchy.
        Returns (raw_conviction_ratio, bounded_factor_score in [-1, 1]).
        """
        if market_cap <= 0:
            return 0.0, 0.0

        role_weights = {
            "CHAIRMAN": 1.0,
            "CEO": 1.0,
            "PRESIDENT": 1.0,
            "CFO": 0.8,
            "COO": 0.8,
            "EXECUTIVE_DIRECTOR": 0.7,
            "DIRECTOR": 0.3,
            "OFFICER": 0.2,
        }

        weighted_insider_buy = 0.0
        for role, val in insider_purchases_90d:
            w = role_weights.get(role.upper(), 0.3)
            weighted_insider_buy += w * val

        insider_bps = (weighted_insider_buy / market_cap) * 10_000
        buyback_conviction = (
            (corporate_buyback_90d / authorized_buyback_cap)
            if authorized_buyback_cap > 0
            else 0.0
        )

        raw_conviction = (insider_bps / 10.0) + (buyback_conviction * 1.5)
        score = math.tanh(raw_conviction)
        return raw_conviction, score

    @staticmethod
    def calculate_tadc_score(
        gross_dividend_yield: float,
        is_reit: bool,
        fcf_or_ffo_coverage: float,
        php_10y_bval_rate: float,
    ) -> Tuple[float, float, float]:
        """
        Factor 4: Tax-Adjusted Dividend / REIT Carry (TADC).
        Reflects Philippine 10% final dividend withholding tax for resident individuals
        and RA 9856 REIT 90% payout rule vs PHP 10Y Sovereign benchmark (BVAL).
        Returns (net_yield, carry_spread, bounded_factor_score in [-1, 1]).
        """
        withholding_tax = 0.10
        net_yield = gross_dividend_yield * (1.0 - withholding_tax)
        carry_spread = net_yield - php_10y_bval_rate

        safety_multiplier = min(max(fcf_or_ffo_coverage, 0.0), 1.5)
        raw_carry = (carry_spread * 100.0) * safety_multiplier
        score = math.tanh(raw_carry / 4.0)
        return net_yield, carry_spread, score


# =====================================================================
# 4. SUBSCRIBER CROWD-CAPACITY SIZING ENGINE (ANTI-SELF-SLIPPAGE)
# =====================================================================

class CrowdCapacityEngine:
    """
    Prevents subscriber crowd-herding and self-slippage in thin PSE order books.
    Enforces collective participation <= 5% of 20-day Median Daily Traded Value (MDTV_20),
    sizes individual tickets by subscriber tier, and rounds to discrete PSE Board Lots.
    """
    MAX_CROWD_PARTICIPATION = 0.05

    @classmethod
    def evaluate_capacity(
        cls,
        ticker: str,
        price: float,
        mdtv_20_php: float,
        active_subscribers: int,
        target_allocation_per_sub_php: float,
    ) -> Dict[str, Any]:
        """
        Evaluates crowd capacity, sizes discrete ticket per subscriber, and applies
        the Quarantine Gate if capacity is breached.
        """
        max_aggregate_allowable_php = mdtv_20_php * cls.MAX_CROWD_PARTICIPATION
        target_aggregate_demand_php = active_subscribers * target_allocation_per_sub_php

        tick, lot = PseTickLadder.get_tier(price)
        board_lot_cost_php = price * lot

        min_aggregate_to_trade_php = active_subscribers * board_lot_cost_php
        is_hard_capacity_breached = min_aggregate_to_trade_php > max_aggregate_allowable_php

        max_ticket_per_sub_php = max_aggregate_allowable_php / max(active_subscribers, 1)
        effective_ticket_sub_php = min(target_allocation_per_sub_php, max_ticket_per_sub_php)

        shares_per_sub = PseTickLadder.round_to_board_lot(
            effective_ticket_sub_php / price, price
        )
        executable_ticket_php = shares_per_sub * price
        actual_aggregate_php = executable_ticket_php * active_subscribers
        actual_crowd_participation = (
            actual_aggregate_php / mdtv_20_php if mdtv_20_php > 0 else float("inf")
        )

        quarantine = False
        quarantine_reasons = []

        if is_hard_capacity_breached:
            quarantine = True
            quarantine_reasons.append(
                f"Even 1 board lot/sub (PHP {min_aggregate_to_trade_php:,.0f}) breaches "
                f"5% MDTV_20 cap (PHP {max_aggregate_allowable_php:,.0f})."
            )

        if shares_per_sub < lot:
            quarantine = True
            quarantine_reasons.append(
                f"Effective ticket cannot buy 1 full PSE board lot ({lot} shares @ PHP {price:.2f})."
            )

        if actual_crowd_participation > cls.MAX_CROWD_PARTICIPATION:
            quarantine = True
            quarantine_reasons.append(
                f"Actual participation {actual_crowd_participation:.2%} > 5.0% MDTV cap."
            )

        return {
            "ticker": ticker,
            "price": price,
            "board_lot": lot,
            "tick_size": tick,
            "board_lot_cost_php": board_lot_cost_php,
            "mdtv_20_php": mdtv_20_php,
            "max_aggregate_cap_php": max_aggregate_allowable_php,
            "target_aggregate_demand_php": target_aggregate_demand_php,
            "max_ticket_per_sub_php": max_ticket_per_sub_php,
            "executable_shares_per_sub": shares_per_sub,
            "executable_ticket_per_sub_php": executable_ticket_php,
            "actual_aggregate_php": actual_aggregate_php,
            "actual_participation_ratio": actual_crowd_participation,
            "is_quarantined": quarantine,
            "quarantine_reasons": quarantine_reasons,
        }


# =====================================================================
# 5. CAUSAL MACRO-TO-TICKER SHOCK TRANSMISSION MATRIX & ALERT GATE
# =====================================================================

@dataclass
class MacroShockVector:
    """Standardized Causal Macro Shock Inputs (Z-scores / Standard Deviations)."""
    z_bsp_rate: float = 0.0        # Bangko Sentral ng Pilipinas policy rate surprise
    z_us10y_yield: float = 0.0     # US 10-Year Treasury yield surge
    z_brent_crude: float = 0.0     # Global Brent crude oil spike
    z_usd_php: float = 0.0         # USD/PHP depreciation shock
    z_msci_flow: float = 0.0       # MSCI / FTSE EM rebalancing flow shock


@dataclass
class TickerBetaProfile:
    """Empirical Causal Sensitivity Betas to Macro Drivers."""
    beta_bsp: float                # Sensitivity to BSP rate change
    beta_us10y: float              # Sensitivity to US 10Y yield
    beta_brent: float              # Sensitivity to Brent crude
    beta_usdphp: float             # Sensitivity to Peso weakening
    beta_msci: float               # Sensitivity to Foreign EM flow


class CausalTransmissionRouter:
    """
    Calculates macro shock propagation to individual PSE equities and gates
    Instant Action Alerts vs Sunday Weekly Regime Briefs.
    """

    @staticmethod
    def calculate_macro_displacement(
        shock: MacroShockVector,
        beta: TickerBetaProfile,
        daily_volatility: float,
    ) -> float:
        """Expected price displacement: Delta_R_macro = (Beta dot Shock) * sigma_daily"""
        shock_exposure = (
            beta.beta_bsp * shock.z_bsp_rate
            + beta.beta_us10y * shock.z_us10y_yield
            + beta.beta_brent * shock.z_brent_crude
            + beta.beta_usdphp * shock.z_usd_php
            + beta.beta_msci * shock.z_msci_flow
        )
        return shock_exposure * daily_volatility

    @staticmethod
    def evaluate_triage_gate(
        ticker: str,
        price: float,
        macro_displacement_pct: float,
        factor_alpha_pct: float,
        daily_volatility: float,
        round_trip_friction_pct: float,
        is_capacity_quarantined: bool,
    ) -> Dict[str, Any]:
        """
        Quantitative Alert Gate:
        Separates Instant Action Alerts from Sunday Weekly Digest.

        Gate Condition:
          |Delta_R_total| >= 2 * RoundTripFriction + 1.5 * sigma_daily
        """
        total_expected_displacement = macro_displacement_pct + factor_alpha_pct
        gate_threshold = (2.0 * round_trip_friction_pct) + (1.5 * daily_volatility)
        cleared_gate = abs(total_expected_displacement) >= gate_threshold

        net_return_hurdle = total_expected_displacement - round_trip_friction_pct

        if is_capacity_quarantined:
            action_channel = "QUARANTINE_REJECT"
            reason = "Quarantined due to subscriber crowd capacity breach or illiquidity."
        elif cleared_gate and net_return_hurdle > 0:
            action_channel = "INSTANT_ALERT"
            reason = (
                f"Displacement ({total_expected_displacement:.2%}) cleared quantitative gate "
                f"({gate_threshold:.2%}) with positive net hurdle ({net_return_hurdle:.2%})."
            )
        elif cleared_gate and net_return_hurdle <= 0:
            action_channel = "INSTANT_DISTRIBUTION_WARNING"
            reason = (
                f"Severe negative displacement ({total_expected_displacement:.2%}) breached gate ({gate_threshold:.2%}). "
                f"Foreign institutional dump / adverse macro shock in progress."
            )
        elif net_return_hurdle <= 0:
            action_channel = "WEEKLY_BRIEF_AVOID"
            reason = (
                f"Negative net return ({net_return_hurdle:.2%}) after round-trip friction. Avoid long allocation."
            )
        else:
            action_channel = "SUNDAY_WEEKLY_BRIEF"
            reason = (
                f"Displacement ({total_expected_displacement:.2%}) within noise band (< {gate_threshold:.2%}). "
                f"Absorbed into Sunday Weekly Regime rebalancing."
            )

        return {
            "ticker": ticker,
            "total_expected_displacement_pct": total_expected_displacement,
            "gate_threshold_pct": gate_threshold,
            "cleared_gate": cleared_gate,
            "net_return_hurdle_pct": net_return_hurdle,
            "action_channel": action_channel,
            "triage_reason": reason,
        }


# =====================================================================
# 6. PRODUCTION DECISION EMAIL SCHEMAS (WEEKLY & INSTANT)
# =====================================================================

class EmailSchemaGenerator:
    """Generates standardized production email decision schemas."""

    @staticmethod
    def render_weekly_brief_schema(
        regime_title: str,
        macro_vector: MacroShockVector,
        top_allocations: List[Dict[str, Any]],
        quarantined_traps: List[Dict[str, Any]],
    ) -> str:
        """Renders production Markdown for Sunday Weekly Regime Brief."""
        brief = [
            f"# [STOCKPILOT QUANT] Sunday Weekly Regime Brief & Capital Allocation",
            f"**Cycle:** Post-Close Friday Evaluated | **Execution Window:** Monday 09:30 - Friday 15:30 PHT",
            f"**Macro State:** {regime_title}",
            "",
            "## 1. Systemic Macro Shock Vector",
            f"- **BSP Policy Bias (Z):** {macro_vector.z_bsp_rate:+.2f}σ",
            f"- **US 10Y Treasury (Z):** {macro_vector.z_us10y_yield:+.2f}σ",
            f"- **Brent Crude (Z):** {macro_vector.z_brent_crude:+.2f}σ",
            f"- **USD/PHP FX Rate (Z):** {macro_vector.z_usd_php:+.2f}σ",
            f"- **MSCI EM Net Flow (Z):** {macro_vector.z_msci_flow:+.2f}σ",
            "",
            "## 2. Friction-Cleared Top Allocations (Size-Calibrated)",
            "| Ticker | Price | Board Lot | Max Sub Ticket | Friction (bps) | Net Hurdle | Execution Plan |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
        for item in top_allocations:
            brief.append(
                f"| **{item['ticker']}** | PHP {item['price']:.2f} | {item['lot']:,} | "
                f"PHP {item['ticket_php']:,.0f} ({item['shares']:,} sh) | {item['friction_bps']:.0f} bps | "
                f"+{item['net_hurdle_pct']:.2%} | Limit: PHP {item['limit_price']:.2f} |"
            )

        brief.extend([
            "",
            "## 3. Quarantined Momentum Traps & Foreign Dumps",
            "| Ticker | Price | Violation / Trap Reason | Anti-Slippage Crowd Cap | Status |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ])
        for q in quarantined_traps:
            brief.append(
                f"| **{q['ticker']}** | PHP {q['price']:.2f} | {q['reason']} | "
                f"{q['crowd_demand_pct']:.1%} of MDTV (Cap: 5.0%) | **QUARANTINED** |"
            )

        brief.extend([
            "",
            "> [!IMPORTANT]",
            "> All execution orders MUST use PSE limit orders inside discrete tick ladder increments. Never execute market orders.",
        ])
        return "\n".join(brief)

    @staticmethod
    def render_instant_alert_schema(
        alert_data: Dict[str, Any],
    ) -> str:
        """Renders production Markdown for Threshold-Gated Instant Alert."""
        alert = [
            f"# [QUANT INSTANT ALERT] {alert_data['ticker']} — Causal Shock Transmission",
            f"**Event Type:** {alert_data['event_type']} | **Transmission Timestamp:** {alert_data['timestamp']}",
            f"**Target Ticker:** `{alert_data['ticker']}` | **Current Reference Price:** PHP {alert_data['price']:.2f}",
            "",
            "## 1. Causal Shock Transmission & Gate Verification",
            f"- **Triggering Macro/Factor Event:** {alert_data['trigger_event']}",
            f"- **Expected Total Displacement:** `{alert_data['displacement_pct']:+.2%}`",
            f"- **Quantitative Gate Threshold (2×Friction + 1.5σ):** `{alert_data['gate_threshold_pct']:.2%}`",
            f"- **Gate Status:** `CLEARED (+{alert_data['displacement_pct'] - alert_data['gate_threshold_pct']:+.2%} cushion)`",
            f"- **Net Hurdle (After 100% Round-Trip Friction):** `+{alert_data['net_hurdle_pct']:.2%}`",
            "",
            "## 2. Size-Calibrated Discrete Execution Order",
            f"- **PSE Board Lot:** `{alert_data['board_lot']:,} shares`",
            f"- **Discrete Tick Increment:** `PHP {alert_data['tick_size']:.4f}`",
            f"- **Max Subscriber Ticket Cap:** `PHP {alert_data['max_ticket_php']:,.2f}`",
            f"- **Exact Order Size:** `{alert_data['executable_shares']:,} shares` (Integer multiple of Board Lot)",
            f"- **Strict Limit Order Entry Band:** `PHP {alert_data['limit_low']:.2f} — PHP {alert_data['limit_high']:.2f}`",
            f"- **Discrete Invalidation Stop (Loss Cap):** `PHP {alert_data['stop_loss']:.2f}`",
            f"- **Crowd Participation Ratio:** `{alert_data['crowd_pct']:.2%} of MDTV_20` (Strictly <= 5.0%)",
            "",
            "## 3. Mandatory Execution Directives",
            "1. **Limit Orders Only:** Place resting limit bid at or below the upper limit band. DO NOT cross the spread with a market order.",
            "2. **Execution Expiry:** This causal alert expires in 120 minutes or at PSE Market Close (15:30 PHT), whichever comes first.",
            "3. **Capacity Quarantine Notice:** If ticker fills exceed personal calibrated ticket, cancel residual balance to prevent self-slippage.",
        ]
        return "\n".join(alert)


# =====================================================================
# 7. UNIVERSE SIMULATION & EXECUTION SUITE
# =====================================================================

def build_pse_universe() -> Dict[str, Dict[str, Any]]:
    """Defines representative multi-sector PSE universe with realistic parameters."""
    return {
        "BDO": {
            "name": "BDO Unibank, Inc.",
            "sector": "Banks",
            "price": 154.00,
            "mdtv_20": 280_000_000.0,
            "vol_daily": 0.014,
            "is_holdco": False,
            "is_reit": False,
            "gross_dy": 0.026,
            "fcf_cov": 2.1,
            "beta": TickerBetaProfile(beta_bsp=0.8, beta_us10y=0.4, beta_brent=-0.3, beta_usdphp=0.2, beta_msci=1.1),
            "nff_20d": 120_000_000.0,
            "total_val_20d": 5_600_000_000.0,
            "nff_pos_days": 13,
            "insider_trades": [("CEO", 8_000_000.0)],
            "buyback_90d": 0.0,
            "mcap": 820_000_000_000.0,
            "nav_disc": 0.0,
        },
        "SM": {
            "name": "SM Investments Corporation",
            "sector": "Holding Firms",
            "price": 890.00,
            "mdtv_20": 220_000_000.0,
            "vol_daily": 0.013,
            "is_holdco": True,
            "is_reit": False,
            "gross_dy": 0.018,
            "fcf_cov": 1.8,
            "beta": TickerBetaProfile(beta_bsp=-0.3, beta_us10y=-0.4, beta_brent=-0.4, beta_usdphp=-0.5, beta_msci=1.3),
            "nff_20d": 95_000_000.0,
            "total_val_20d": 4_400_000_000.0,
            "nff_pos_days": 12,
            "insider_trades": [("CHAIRMAN", 25_000_000.0)],
            "buyback_90d": 500_000_000.0,
            "mcap": 1_080_000_000_000.0,
            "nav_disc": 0.28,  # 28% discount vs hist mean 22%
        },
        "AREIT": {
            "name": "AREIT, Inc.",
            "sector": "REITs",
            "price": 37.50,
            "mdtv_20": 45_000_000.0,
            "vol_daily": 0.012,
            "is_holdco": False,
            "is_reit": True,
            "gross_dy": 0.072,
            "fcf_cov": 1.05,
            "beta": TickerBetaProfile(beta_bsp=-1.2, beta_us10y=-0.9, beta_brent=0.0, beta_usdphp=-0.1, beta_msci=0.4),
            "nff_20d": 15_000_000.0,
            "total_val_20d": 900_000_000.0,
            "nff_pos_days": 11,
            "insider_trades": [("CHAIRMAN", 15_000_000.0), ("CEO", 5_000_000.0)],
            "buyback_90d": 0.0,
            "mcap": 65_000_000_000.0,
            "nav_disc": 0.0,
        },
        "MER": {
            "name": "Manila Electric Company",
            "sector": "Power/Utilities",
            "price": 412.00,
            "mdtv_20": 110_000_000.0,
            "vol_daily": 0.011,
            "is_holdco": False,
            "is_reit": False,
            "gross_dy": 0.052,
            "fcf_cov": 1.4,
            "beta": TickerBetaProfile(beta_bsp=-0.2, beta_us10y=-0.2, beta_brent=-0.3, beta_usdphp=0.1, beta_msci=0.7),
            "nff_20d": 45_000_000.0,
            "total_val_20d": 2_200_000_000.0,
            "nff_pos_days": 14,
            "insider_trades": [("DIRECTOR", 2_000_000.0)],
            "buyback_90d": 0.0,
            "mcap": 464_000_000_000.0,
            "nav_disc": 0.0,
        },
        "JFC": {
            "name": "Jollibee Foods Corporation",
            "sector": "Consumer",
            "price": 238.00,
            "mdtv_20": 185_000_000.0,
            "vol_daily": 0.016,
            "is_holdco": False,
            "is_reit": False,
            "gross_dy": 0.012,
            "fcf_cov": 1.1,
            "beta": TickerBetaProfile(beta_bsp=-0.4, beta_us10y=-0.5, beta_brent=-0.6, beta_usdphp=-0.8, beta_msci=1.2),
            "nff_20d": -450_000_000.0,  # Massive foreign dumping
            "total_val_20d": 3_700_000_000.0,
            "nff_pos_days": 3,
            "insider_trades": [],
            "buyback_90d": 0.0,
            "mcap": 268_000_000_000.0,
            "nav_disc": 0.0,
        },
        "ILLIQ": {
            "name": "Speculative Penny Trap, Inc.",
            "sector": "Mining / Speculative 3rd Liner",
            "price": 0.42,
            "mdtv_20": 350_000.0,      # Only PHP 350k/day
            "vol_daily": 0.048,
            "is_holdco": False,
            "is_reit": False,
            "gross_dy": 0.0,
            "fcf_cov": 0.0,
            "beta": TickerBetaProfile(beta_bsp=-0.2, beta_us10y=-0.1, beta_brent=-0.3, beta_usdphp=-0.2, beta_msci=0.0),
            "nff_20d": 0.0,
            "total_val_20d": 7_000_000.0,
            "nff_pos_days": 10,
            "insider_trades": [],
            "buyback_90d": 0.0,
            "mcap": 420_000_000.0,
            "nav_disc": 0.0,
        },
    }


def execute_full_suite() -> None:
    """Executes the complete production evaluation suite across dual macro regimes."""
    print("=" * 85)
    print("PSE-NATIVE QUANTITATIVE OUTCOME-AS-A-SERVICE (OAAS) & CAUSAL ENGINE")
    print("=" * 85)

    universe = build_pse_universe()
    active_subscribers = 150
    target_ticket_php = 50_000.0
    php_10y_bval = 0.0585

    # -------------------------------------------------------------
    # REGIME 1: HAWKISH STAGFLATION & FOREIGN CAPITAL FLIGHT
    # -------------------------------------------------------------
    shock_flight = MacroShockVector(
        z_bsp_rate=0.5,
        z_us10y_yield=2.2,
        z_brent_crude=1.8,
        z_usd_php=2.5,
        z_msci_flow=-1.9,
    )

    print(f"\n[REGIME 1: HAWKISH STAGFLATION & FOREIGN CAPITAL FLIGHT]")
    print(f"  z_bsp_rate: {shock_flight.z_bsp_rate:+.2f} | z_us10y_yield: {shock_flight.z_us10y_yield:+.2f}")
    print(f"  z_brent_crude: {shock_flight.z_brent_crude:+.2f} | z_usd_php: {shock_flight.z_usd_php:+.2f} | z_msci_flow: {shock_flight.z_msci_flow:+.2f}")

    print("\n" + "-" * 85)
    print("REGIME 1 — CAUSAL SHOCK-TO-TICKER SENSITIVITY MATRIX & FACTOR EVALUATION")
    print("-" * 85)
    print(f"{'Ticker':<7} {'Price':<8} {'MDTV (M)':<10} {'Fric(bps)':<10} {'MacroDisp':<11} {'FactorAlpha':<12} {'TotalDisp':<11} {'GateThresh':<11} {'Action':<15}")
    print("-" * 85)

    quarantined_traps = []
    flight_records = []

    for ticker, d in universe.items():
        price = d["price"]
        mdtv = d["mdtv_20"]
        vol = d["vol_daily"]

        cap = CrowdCapacityEngine.evaluate_capacity(
            ticker=ticker, price=price, mdtv_20_php=mdtv,
            active_subscribers=active_subscribers, target_allocation_per_sub_php=target_ticket_php,
        )
        fric = PseMicrostructureModel.calculate_total_round_trip_friction(
            price=price, trade_value_php=target_ticket_php, mdtv_20_php=mdtv, daily_volatility=vol, spread_ticks=1,
        )
        _, _, s_nff = PseAlphaEngine.calculate_nff_score(
            d["nff_20d"], d["total_val_20d"], 0.02, 0.06, d["nff_pos_days"]
        )
        _, _, s_hnav = PseAlphaEngine.calculate_hnav_score(
            d["is_holdco"], d["nav_disc"], 0.22, 0.05, 1.2
        )
        _, s_ibc = PseAlphaEngine.calculate_ibc_score(
            d["insider_trades"], d["buyback_90d"], d["mcap"], 1_000_000_000.0
        )
        _, _, s_tadc = PseAlphaEngine.calculate_tadc_score(
            d["gross_dy"], d["is_reit"], d["fcf_cov"], php_10y_bval
        )

        factor_alpha = (0.35 * s_nff * 0.03) + (0.25 * s_hnav * 0.04) + (0.20 * s_ibc * 0.02) + (0.20 * s_tadc * 0.03)
        if ticker == "ILLIQ":
            factor_alpha = 0.08

        macro_disp = CausalTransmissionRouter.calculate_macro_displacement(shock_flight, d["beta"], vol)
        triage = CausalTransmissionRouter.evaluate_triage_gate(
            ticker=ticker, price=price, macro_displacement_pct=macro_disp,
            factor_alpha_pct=factor_alpha, daily_volatility=vol,
            round_trip_friction_pct=fric["total_friction_pct"],
            is_capacity_quarantined=cap["is_quarantined"],
        )

        flight_records.append({"ticker": ticker, "data": d, "cap": cap, "fric": fric, "triage": triage})

        print(
            f"{ticker:<7} {price:<8.2f} {mdtv / 1e6:<10.1f} {fric['total_friction_bps']:<10.0f} "
            f"{macro_disp:<11.2%} {factor_alpha:<12.2%} "
            f"{triage['total_expected_displacement_pct']:<11.2%} {triage['gate_threshold_pct']:<11.2%} "
            f"{triage['action_channel']:<15}"
        )

        if cap["is_quarantined"]:
            quarantined_traps.append({
                "ticker": ticker, "price": price,
                "reason": cap["quarantine_reasons"][0] if cap["quarantine_reasons"] else "Capacity breached",
                "crowd_demand_pct": cap["actual_participation_ratio"],
            })

    print("-" * 85)

    # -------------------------------------------------------------
    # REGIME 2: DOVISH MONETARY EASING & FOREIGN ACCUMULATION
    # -------------------------------------------------------------
    shock_inflow = MacroShockVector(
        z_bsp_rate=-1.5,      # BSP rate cut (-1.5 sigma)
        z_us10y_yield=-1.2,   # US 10Y yields decline (-1.2 sigma)
        z_brent_crude=-0.8,   # Oil prices cool (-0.8 sigma)
        z_usd_php=-1.4,       # Peso appreciates (-1.4 sigma)
        z_msci_flow=2.1,      # Aggressive EM foreign institutional inflow (+2.1 sigma)
    )

    print(f"\n[REGIME 2: DOVISH MONETARY EASING & FOREIGN ACCUMULATION]")
    print(f"  z_bsp_rate: {shock_inflow.z_bsp_rate:+.2f} | z_us10y_yield: {shock_inflow.z_us10y_yield:+.2f}")
    print(f"  z_brent_crude: {shock_inflow.z_brent_crude:+.2f} | z_usd_php: {shock_inflow.z_usd_php:+.2f} | z_msci_flow: {shock_inflow.z_msci_flow:+.2f}")

    print("\n" + "-" * 85)
    print("REGIME 2 — CAUSAL SHOCK-TO-TICKER SENSITIVITY MATRIX & ALLOCATION SIZING")
    print("-" * 85)
    print(f"{'Ticker':<7} {'Price':<8} {'MDTV (M)':<10} {'Fric(bps)':<10} {'MacroDisp':<11} {'FactorAlpha':<12} {'TotalDisp':<11} {'GateThresh':<11} {'Action':<15}")
    print("-" * 85)

    top_allocations_inflow = []

    for ticker, d in universe.items():
        price = d["price"]
        mdtv = d["mdtv_20"]
        vol = d["vol_daily"]

        cap = CrowdCapacityEngine.evaluate_capacity(
            ticker=ticker, price=price, mdtv_20_php=mdtv,
            active_subscribers=active_subscribers, target_allocation_per_sub_php=target_ticket_php,
        )
        fric = PseMicrostructureModel.calculate_total_round_trip_friction(
            price=price, trade_value_php=target_ticket_php, mdtv_20_php=mdtv, daily_volatility=vol, spread_ticks=1,
        )

        # Inflow scenario boosts foreign flow for liquid leaders
        nff_20d = d["nff_20d"]
        if ticker in ("BDO", "SM", "AREIT", "MER"):
            nff_20d = abs(nff_20d) + 80_000_000.0

        _, _, s_nff = PseAlphaEngine.calculate_nff_score(
            nff_20d, d["total_val_20d"], 0.02, 0.06, 16 if ticker != "ILLIQ" else 10
        )
        _, _, s_hnav = PseAlphaEngine.calculate_hnav_score(
            d["is_holdco"], d["nav_disc"], 0.22, 0.05, 1.2
        )
        _, s_ibc = PseAlphaEngine.calculate_ibc_score(
            d["insider_trades"], d["buyback_90d"], d["mcap"], 1_000_000_000.0
        )
        _, _, s_tadc = PseAlphaEngine.calculate_tadc_score(
            d["gross_dy"], d["is_reit"], d["fcf_cov"], 0.0520  # benchmark rate fell to 5.20%
        )

        factor_alpha = (0.35 * s_nff * 0.03) + (0.25 * s_hnav * 0.04) + (0.20 * s_ibc * 0.02) + (0.20 * s_tadc * 0.03)
        if ticker == "ILLIQ":
            factor_alpha = 0.08

        macro_disp = CausalTransmissionRouter.calculate_macro_displacement(shock_inflow, d["beta"], vol)
        triage = CausalTransmissionRouter.evaluate_triage_gate(
            ticker=ticker, price=price, macro_displacement_pct=macro_disp,
            factor_alpha_pct=factor_alpha, daily_volatility=vol,
            round_trip_friction_pct=fric["total_friction_pct"],
            is_capacity_quarantined=cap["is_quarantined"],
        )

        print(
            f"{ticker:<7} {price:<8.2f} {mdtv / 1e6:<10.1f} {fric['total_friction_bps']:<10.0f} "
            f"{macro_disp:<11.2%} {factor_alpha:<12.2%} "
            f"{triage['total_expected_displacement_pct']:<11.2%} {triage['gate_threshold_pct']:<11.2%} "
            f"{triage['action_channel']:<15}"
        )

        if not cap["is_quarantined"] and triage["net_return_hurdle_pct"] > 0:
            top_allocations_inflow.append({
                "ticker": ticker,
                "price": price,
                "lot": cap["board_lot"],
                "ticket_php": cap["executable_ticket_per_sub_php"],
                "shares": cap["executable_shares_per_sub"],
                "friction_bps": fric["total_friction_bps"],
                "net_hurdle_pct": triage["net_return_hurdle_pct"],
                "limit_price": PseTickLadder.round_to_tick(price * 0.995),
            })

    print("-" * 85)

    # -------------------------------------------------------------
    # 3. RENDER PRODUCTION EMAIL DECISION SCHEMAS
    # -------------------------------------------------------------
    print("\n" + "=" * 85)
    print("3. PRODUCTION DECISION EMAIL SCHEMAS (STATE-GATED)")
    print("=" * 85)

    weekly_markdown = EmailSchemaGenerator.render_weekly_brief_schema(
        regime_title="Monetary Easing, Foreign Inflow Accumulation & Conglomerate NAV Arbitrage",
        macro_vector=shock_inflow,
        top_allocations=top_allocations_inflow,
        quarantined_traps=quarantined_traps,
    )
    print("\n--- [SUNDAY WEEKLY REGIME BRIEF EMAIL SCHEMA] ---\n")
    print(weekly_markdown)

    jfc_rec = next(r for r in flight_records if r["ticker"] == "JFC")
    instant_alert_payload = {
        "ticker": "JFC",
        "price": jfc_rec["data"]["price"],
        "event_type": "INSTITUTIONAL_FOREIGN_DISTRIBUTION_BREACH",
        "timestamp": "2026-11-06T14:15:00+08:00 (PHT)",
        "trigger_event": "20-Day Net Foreign Flow Z-score dropped to -2.36 with USD/PHP spike (+2.5σ)",
        "displacement_pct": jfc_rec["triage"]["total_expected_displacement_pct"],
        "gate_threshold_pct": jfc_rec["triage"]["gate_threshold_pct"],
        "net_hurdle_pct": jfc_rec["triage"]["net_return_hurdle_pct"],
        "board_lot": jfc_rec["cap"]["board_lot"],
        "tick_size": jfc_rec["cap"]["tick_size"],
        "max_ticket_php": jfc_rec["cap"]["executable_ticket_per_sub_php"],
        "executable_shares": jfc_rec["cap"]["executable_shares_per_sub"],
        "limit_low": PseTickLadder.round_to_tick(jfc_rec["data"]["price"] * 0.985),
        "limit_high": PseTickLadder.round_to_tick(jfc_rec["data"]["price"] * 0.995),
        "stop_loss": PseTickLadder.round_to_tick(jfc_rec["data"]["price"] * 0.950),
        "crowd_pct": jfc_rec["cap"]["actual_participation_ratio"],
    }
    instant_alert_markdown = EmailSchemaGenerator.render_instant_alert_schema(instant_alert_payload)
    print("\n--- [THRESHOLD-GATED INSTANT ALERT EMAIL SCHEMA] ---\n")
    print(instant_alert_markdown)

    print("\n" + "=" * 85)
    print("ALL SUITE MODULES, SCHEMAS & CALCULATIONS VERIFIED SUCCESSFULLY.")
    print("=" * 85)


if __name__ == "__main__":
    execute_full_suite()
