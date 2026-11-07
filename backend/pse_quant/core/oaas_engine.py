"""
backend/pse_quant/core/oaas_engine.py — PSE-Native Quantitative Outcome-as-a-Service (OaaS)
==========================================================================================
Deterministic Microstructure, Causal Shock Transmission, and Sizing Modules.
"""

from __future__ import annotations
import math
import sys
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


class PseStatutoryFees:
    """Exact statutory transaction costs for the Philippine Stock Exchange (PSE)."""
    BROKER_COMMISSION_RATE = 0.0025          # 0.25% min broker commission
    VAT_RATE = 0.12                          # 12% VAT on commission (0.0025 * 0.12 = 0.00030)
    SEC_FEE_RATE = 0.00005                   # 0.005% SEC transaction fee
    PSE_TRANSACTION_FEE_RATE = 0.00005       # 0.005% PSE transaction fee
    SCCP_CLEARING_FEE_RATE = 0.00010         # 0.010% SCCP clearing fee
    MIN_BROKER_COMMISSION_PHP = 20.00        # Minimum PHP 20 broker fee per transaction
    STOCK_TRANSACTION_TAX_RATE = 0.0060      # 0.60% Stock Transaction Tax (STT) on gross sell value

    @classmethod
    def buy_side_pct(cls) -> float:
        return (
            cls.BROKER_COMMISSION_RATE
            + (cls.BROKER_COMMISSION_RATE * cls.VAT_RATE)
            + cls.SEC_FEE_RATE
            + cls.PSE_TRANSACTION_FEE_RATE
            + cls.SCCP_CLEARING_FEE_RATE
        )

    @classmethod
    def sell_side_pct(cls) -> float:
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
        return cls.buy_side_pct() + cls.sell_side_pct()

    @classmethod
    def calculate_exact_fees(cls, buy_value: float, sell_value: float) -> Dict[str, float]:
        buy_comm = max(buy_value * cls.BROKER_COMMISSION_RATE, cls.MIN_BROKER_COMMISSION_PHP)
        buy_vat = buy_comm * cls.VAT_RATE
        buy_sec = buy_value * cls.SEC_FEE_RATE
        buy_pse = buy_value * cls.PSE_TRANSACTION_FEE_RATE
        buy_sccp = buy_value * cls.SCCP_CLEARING_FEE_RATE
        total_buy = buy_comm + buy_vat + buy_sec + buy_pse + buy_sccp

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
    """Official Revised PSE Board Lot and Discrete Tick Size Schedule."""
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
        if price <= 0:
            raise ValueError(f"Invalid price: {price}. Price must be positive.")
        for p_min, p_max, tick, lot in cls.LADDER:
            if p_min <= price <= p_max:
                return tick, lot
        return 5.0000, 5

    @classmethod
    def round_to_tick(cls, price: float) -> float:
        tick, _ = cls.get_tier(price)
        return round(round(price / tick) * tick, 4)

    @classmethod
    def round_to_board_lot(cls, shares: float, price: float) -> int:
        _, lot = cls.get_tier(price)
        return int(math.floor(shares / lot) * lot)

    @classmethod
    def discrete_tick_spread_pct(cls, price: float, spread_ticks: int = 1) -> float:
        tick, _ = cls.get_tier(price)
        return (tick * spread_ticks) / price


class PseMicrostructureModel:
    """Square-Root Amihud Market Impact Model calibrated to PSE thin order books."""
    LAMBDA_PSE = 0.55

    @classmethod
    def calculate_price_impact(
        cls,
        trade_value_php: float,
        mdtv_20_php: float,
        daily_volatility: float,
    ) -> float:
        if mdtv_20_php <= 0:
            return 1.0
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


class PseAlphaEngine:
    """Formulates 4 PSE-native alpha factors."""

    @staticmethod
    def calculate_nff_score(
        net_foreign_flow_20d: float,
        total_traded_value_20d: float,
        hist_nff_ratio_mean: float,
        hist_nff_ratio_std: float,
        positive_foreign_days_20d: int,
    ) -> Tuple[float, float, float]:
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
        weighted_insider_buy = sum(role_weights.get(r.upper(), 0.3) * v for r, v in insider_purchases_90d)
        insider_bps = (weighted_insider_buy / market_cap) * 10_000
        buyback_conviction = (corporate_buyback_90d / authorized_buyback_cap) if authorized_buyback_cap > 0 else 0.0
        raw_conviction = (insider_bps / 10.0) + (buyback_conviction * 1.5)
        return raw_conviction, math.tanh(raw_conviction)

    @staticmethod
    def calculate_tadc_score(
        gross_dividend_yield: float,
        is_reit: bool,
        fcf_or_ffo_coverage: float,
        php_10y_bval_rate: float,
    ) -> Tuple[float, float, float]:
        withholding_tax = 0.10
        net_yield = gross_dividend_yield * (1.0 - withholding_tax)
        carry_spread = net_yield - php_10y_bval_rate
        safety_multiplier = min(max(fcf_or_ffo_coverage, 0.0), 1.5)
        raw_carry = (carry_spread * 100.0) * safety_multiplier
        return net_yield, carry_spread, math.tanh(raw_carry / 4.0)


class CrowdCapacityEngine:
    """Subscriber Crowd-Capacity Sizing Engine (Anti-Self-Slippage)."""
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
        max_aggregate_allowable_php = mdtv_20_php * cls.MAX_CROWD_PARTICIPATION
        target_aggregate_demand_php = active_subscribers * target_allocation_per_sub_php

        tick, lot = PseTickLadder.get_tier(price)
        board_lot_cost_php = price * lot

        min_aggregate_to_trade_php = active_subscribers * board_lot_cost_php
        is_hard_capacity_breached = min_aggregate_to_trade_php > max_aggregate_allowable_php

        max_ticket_per_sub_php = max_aggregate_allowable_php / max(active_subscribers, 1)
        effective_ticket_sub_php = min(target_allocation_per_sub_php, max_ticket_per_sub_php)

        shares_per_sub = PseTickLadder.round_to_board_lot(effective_ticket_sub_php / price, price)
        executable_ticket_php = shares_per_sub * price
        actual_aggregate_php = executable_ticket_php * active_subscribers
        actual_crowd_participation = actual_aggregate_php / mdtv_20_php if mdtv_20_php > 0 else float("inf")

        quarantine = False
        quarantine_reasons = []

        if is_hard_capacity_breached:
            quarantine = True
            quarantine_reasons.append(
                f"Even 1 board lot/sub (PHP {min_aggregate_to_trade_php:,.0f}) breaches 5% MDTV_20 cap (PHP {max_aggregate_allowable_php:,.0f})."
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


@dataclass
class MacroShockVector:
    z_bsp_rate: float = 0.0
    z_us10y_yield: float = 0.0
    z_brent_crude: float = 0.0
    z_usd_php: float = 0.0
    z_msci_flow: float = 0.0


@dataclass
class TickerBetaProfile:
    beta_bsp: float
    beta_us10y: float
    beta_brent: float
    beta_usdphp: float
    beta_msci: float


class CausalTransmissionRouter:
    @staticmethod
    def calculate_macro_displacement(
        shock: MacroShockVector,
        beta: TickerBetaProfile,
        daily_volatility: float,
    ) -> float:
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
        total_expected_displacement = macro_displacement_pct + factor_alpha_pct
        gate_threshold = (2.0 * round_trip_friction_pct) + (1.5 * daily_volatility)
        cleared_gate = abs(total_expected_displacement) >= gate_threshold
        net_return_hurdle = total_expected_displacement - round_trip_friction_pct

        if is_capacity_quarantined:
            action_channel = "QUARANTINE_REJECT"
            reason = "Quarantined due to subscriber crowd capacity breach or illiquidity."
        elif cleared_gate and net_return_hurdle > 0:
            action_channel = "INSTANT_ALERT"
            reason = f"Displacement ({total_expected_displacement:.2%}) cleared quantitative gate ({gate_threshold:.2%})."
        elif cleared_gate and net_return_hurdle <= 0:
            action_channel = "INSTANT_DISTRIBUTION_WARNING"
            reason = f"Severe negative displacement ({total_expected_displacement:.2%}) breached gate ({gate_threshold:.2%})."
        elif net_return_hurdle <= 0:
            action_channel = "WEEKLY_BRIEF_AVOID"
            reason = f"Negative net return ({net_return_hurdle:.2%}) after round-trip friction."
        else:
            action_channel = "SUNDAY_WEEKLY_BRIEF"
            reason = f"Displacement ({total_expected_displacement:.2%}) within noise band (< {gate_threshold:.2%})."

        return {
            "ticker": ticker,
            "total_expected_displacement_pct": total_expected_displacement,
            "gate_threshold_pct": gate_threshold,
            "cleared_gate": cleared_gate,
            "net_return_hurdle_pct": net_return_hurdle,
            "action_channel": action_channel,
            "triage_reason": reason,
        }
