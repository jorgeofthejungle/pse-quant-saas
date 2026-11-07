"""
backend/pse_quant/core/fact_compiler.py — Taglish Fact Card Compiler & Done-For-You Investment Menu
===================================================================================================
Addresses the Philippine retail investment knowledge gap ("Ano po maganda bilhin?") by compiling
audited PSE financial metrics into a clean 4-part Fact Card + Seasoned Numbers toggle:
  1. Verdict: Clear decision badge & natural Taglish summary.
  2. Peso Value Test: How much you pay for every ₱1.00 of true business value (Price vs. Fair Value).
  3. Net Dividend per ₱10k: Annual cash dividend after the 10% tax vs. traditional bank savings.
  4. Health: Profitability (ROE) and debt safety (Debt-to-Equity) in plain Taglish.
  + Seasoned Numbers Toggle: Full 3-Layer scores (Health, Improvement, Persistence), MoS %, BVAL spread.
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Optional, List, Dict


# ── Constants ─────────────────────────────────────────────────
PH_DIVIDEND_TAX_RATE = 0.10          # 10% statutory final withholding tax on cash dividends
TRADITIONAL_BANK_SAVINGS_RATE = 0.25 # 0.25% typical PH traditional bank savings rate (%)
BENCHMARK_10Y_BVAL_PCT = 5.85        # 5.85% PHP 10-Year Sovereign BVAL Benchmark (%)

# ── Curated PSE Company Moat & Risk Intelligence ──────────────
PSE_COMPANY_INTEL: Dict[str, Dict[str, str]] = {
    "AREIT": {
        "moat": "Flagship commercial REIT ng Ayala Land na may long-term leases sa Grade-A offices, malls, at industrial land.",
        "risk": "Bantayan: Interest rate movements at BPO office occupancy renewals.",
    },
    "DMC": {
        "moat": "Diversified engineering, coal/power (Semirara), water (Maynilad), at real estate conglomerate ng Consunji group.",
        "risk": "Bantayan: Global coal at power spot price fluctuations na nakakaapekto sa special dividends.",
    },
    "BDO": {
        "moat": "#1 largest universal bank sa Pilipinas (Sy group) na may pinakamalawak na branch at low-cost CASA deposit network.",
        "risk": "Bantayan: BSP interest rate cuts na maaaring magpaliit ng net interest margins (NIM).",
    },
    "MER": {
        "moat": "Exclusive regulated power distribution utility sa Metro Manila at karatig-probinsya na may steady cash flow.",
        "risk": "Bantayan: ERC regulatory tariff resets at power generation capex commitments.",
    },
    "ICT": {
        "moat": "Global port terminal operator (Razon group) na may mataas na pricing power sa 20+ bansa.",
        "risk": "Bantayan: Global trade volume slowdowns at mataas na current valuation premium.",
    },
    "AC": {
        "moat": "Pinakamatandang premier conglomerate sa bansa (BPI, Ayala Land, Globe, ACEN) na nagte-trade sa conglomerate discount.",
        "risk": "Bantayan: Capital expenditure drag mula sa ACEN renewables at emerging digital units.",
    },
    "ALI": {
        "moat": "Premier master-planned estate developer (BGC, Makati, Nuvali) na may malaking landbank at commercial leasing base.",
        "risk": "Bantayan: High mortgage rates na nagpapabagal sa middle-income residential presales.",
    },
    "SMPH": {
        "moat": "Dominant mall operator sa Pilipinas (~90+ malls) na may matatag na recurring rental cash flow.",
        "risk": "Bantayan: Manila Bay reclamation delays at premium valuation multiple.",
    },
    "MEG": {
        "moat": "Pioneer ng live-work-play townships (Eastwood, McKinley Hill) na may malaking BPO office leasing portfolio.",
        "risk": "Bantayan: POGO/offshore gaming exit headwinds at condo inventory turnover sa Metro Manila.",
    },
    "FLI": {
        "moat": "Mid-market housing at Alabang commercial developer ng Gotianun group na nagte-trade nang malaki sa ibaba ng book value.",
        "risk": "Bantayan: Negative free cash flow kapag mataas ang landbanking at construction capex.",
    },
    "GLO": {
        "moat": "Leading mobile telecom at fintech ecosystem (GCash/Mynt) na may malakas na enterprise data growth.",
        "risk": "Bantayan: Mabigat na 5G/fiber capex debt servicing at kumpetisyon sa mobile data.",
    },
    "URC": {
        "moat": "Leading branded snackfoods at beverage manufacturer (Gokongwei group) sa Pilipinas at ASEAN.",
        "risk": "Bantayan: Raw material inflation (asukal, trigo, packaging) at ASEAN currency swings.",
    },
    "WLCON": {
        "moat": "Leading big-box home improvement at construction retail chain sa Pilipinas.",
        "risk": "Bantayan: Mahinang same-store sales growth habang mabagal ang private residential construction.",
    },
    "BPI": {
        "moat": "Tier-1 universal bank ng Ayala group na kilala sa conservative asset quality at digital banking leadership.",
        "risk": "Bantayan: Consumer loan delinquency trends habang lumalaki ang unsecured credit card book.",
    },
    "MBT": {
        "moat": "Top-3 universal bank (Ty group) na may pinakamataas na capital adequacy buffer at malaking undervalued discount.",
        "risk": "Bantayan: Mas mabagal na loan growth kumpara sa BDO at BPI.",
    },
    "SM": {
        "moat": "Pinakamalaking Philippine proxy conglomerate (SM Retail, BDO, Chinabank, SM Prime) ng Sy family.",
        "risk": "Bantayan: Consumer spending sensitivity sa inflation at holding company discount.",
    },
    "JFC": {
        "moat": "#1 dominant quick-service restaurant giant sa Pilipinas (Jollibee, Mang Inasal, Chowking) na may global expansion.",
        "risk": "Bantayan: International acquisition integration costs (Coffee Bean, Smashburger) at food cost inflation.",
    },
    "BLOOM": {
        "moat": "Integrated resort at casino operator (Solaire Entertainment City at Solaire Resort North).",
        "risk": "Bantayan: VIP gaming drop weakness at mataas na debt servicing mula sa Solaire North expansion.",
    },
    "AGI": {
        "moat": "Holding company ni Andrew Tan (Megaworld, Emperador global brandy/whisky, Newport World Resorts, Golden Arches/McDonald's PH).",
        "risk": "Bantayan: European liquor margin compression sa Emperador at casino headwinds.",
    },
    "SCC": {
        "moat": "Integrated coal mining at baseload power producer (Consunji group) na kilala sa mataas na special cash dividends.",
        "risk": "Bantayan: Semirara coal mining contract expiration risk (2027) at coal price normalization.",
    },
    "CREIT": {
        "moat": "First renewable energy REIT sa Pilipinas na kumikita sa guaranteed solar farm land leases + variable revenue share.",
        "risk": "Bantayan: Concentration risk sa isang major sponsor group (Citicore Renewable Energy).",
    },
    "DITO": {
        "moat": "3rd telco challenger na nagpapatakbo ng 4G/5G network infrastructure sa Pilipinas.",
        "risk": "Red Flag: Tuloy-tuloy na bilyun-bilyong net loss, negative shareholder equity (capital deficiency), at mabigat na foreign/local debt.",
    },
    "CEB": {
        "moat": "Pinakamalaking domestic at regional low-cost airline sa Pilipinas (Gokongwei group).",
        "risk": "Red Flag: Napakataas na aircraft lease at debt leverage (6.59x D/E) at volatile na jet fuel/forex costs.",
    },
    "TEL": {
        "moat": "Pinakamalaking integrated fixed-line broadband (PLDT Home/Enterprise) at mobile (Smart) network sa bansa.",
        "risk": "Red Flag: Lumagpas sa 3.0x non-financial debt-to-equity safety cap (3.99x D/E) matapos ang heavy capex cycle.",
    },
}


@dataclass
class FactCard:
    """The 4-part Taglish Fact Card for beginners and everyday Filipino investors."""
    bucket_tag: str
    bucket_label: str
    verdict: str
    peso_value_test: str
    net_dividend_per_10k: str
    health: str

    # Backwards-compatible aliases for any legacy callers
    @property
    def headline_verdict(self) -> str:
        return self.verdict

    @property
    def piso_value_fact(self) -> str:
        return self.peso_value_test

    @property
    def dividend_cash_fact(self) -> str:
        return self.net_dividend_per_10k

    @property
    def business_safety_fact(self) -> str:
        return self.health


@dataclass
class SeasonedNumbers:
    """Hard quantitative breakdown toggled by seasoned investors."""
    composite_score: float
    health_score: Optional[float]
    improvement_score: Optional[float]
    persistence_score: Optional[float]
    confidence_pct: float
    current_price_php: float
    intrinsic_value_php: Optional[float]
    margin_of_safety_pct: Optional[float]
    gross_dividend_yield_pct: float
    net_dividend_yield_pct: float
    net_annual_cash_per_10k_php: float
    spread_vs_bval_bps: float
    roe_pct: Optional[float]
    net_margin_pct: Optional[float]
    debt_to_equity: Optional[float]
    mos_target_price_php: Optional[float] = None
    ddm_value_php: Optional[float] = None
    pe_value_php: Optional[float] = None
    dcf_value_php: Optional[float] = None
    eps_trajectory_str: Optional[str] = None
    revenue_cagr_pct: Optional[float] = None
    dividend_cagr_pct: Optional[float] = None
    fcf_yield_pct: Optional[float] = None
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    required_return_pct: Optional[float] = None


class DoneForYouFactCompiler:
    """
    Compiles raw quantitative stock records into structured Fact Cards (Verdict, Peso Value Test,
    Net Dividend per ₱10k, Health) + Seasoned Numbers, plus an instant PSE Edge Stock Reality Check.
    """

    @staticmethod
    def _to_billions(val: Optional[float]) -> float:
        """Normalizes raw PHP, thousands, or millions into PHP Billions."""
        if val is None:
            return 0.0
        v = abs(float(val))
        if v >= 1e9:
            return v / 1e9
        if v >= 1e6:
            return v / 1e6
        return v / 1e3

    @classmethod
    def classify_goal_bucket(
        cls,
        score: float,
        mos_pct: Optional[float],
        net_div_yield_pct: float,
        debt_to_equity: Optional[float] = None,
        is_illiquid: bool = False,
        is_bank: bool = False,
        filter_passed: bool = True,
        net_income: Optional[float] = None,
        equity: Optional[float] = None,
        raw_score: Optional[float] = None,
    ) -> tuple[str, str]:
        """
        Categorizes a stock into one of 4 clear buckets:
          1. PASSIVE_INCOME_CHAMPION
          2. UNDERVALUED_BLUE_CHIP
          3. QUALITY_COMPOUNDER
          4. VALUE_OR_HYPE_TRAP
        """
        mos = mos_pct if mos_pct is not None else 0.0
        de = debt_to_equity if debt_to_equity is not None else 0.5
        excess_leverage = (not is_bank) and (de > 3.0)
        negative_fundamentals = (net_income is not None and net_income < 0) or (equity is not None and equity <= 0)
        eff_score = max(score, float(raw_score) * 0.80) if (raw_score is not None and filter_passed) else score

        if (
            not filter_passed
            or is_illiquid
            or negative_fundamentals
            or eff_score < 50.0
            or excess_leverage
            or (mos < -20.0 and eff_score < 65.0)
        ):
            return (
                "VALUE_OR_HYPE_TRAP",
                "Hype Trap / Avoid For Now",
            )

        if net_div_yield_pct >= 4.5 and mos >= -5.0 and eff_score >= 57.0:
            return (
                "PASSIVE_INCOME_CHAMPION",
                "Option A: Steady Dividend Payer",
            )

        if mos >= 15.0 and eff_score >= 58.0:
            return (
                "UNDERVALUED_BLUE_CHIP",
                "Option B: Undervalued Blue Chip",
            )

        return (
            "QUALITY_COMPOUNDER",
            "Option C: Quality Growth Compounder",
        )

    @classmethod
    def compile_stock_option(
        cls,
        stock_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Takes a ranked stock dict and compiles the 4-part Fact Card + Seasoned Numbers.
        """
        ticker = str(stock_data.get("ticker", "UNKNOWN")).upper()
        name = str(stock_data.get("name", ticker))
        sector = str(stock_data.get("sector", "General"))
        score = float(stock_data.get("score") or 0.0)
        confidence = float(stock_data.get("confidence") or 1.0)
        price = float(stock_data.get("current_price") or 0.0)
        iv = stock_data.get("intrinsic_value")
        iv_float = float(iv) if iv is not None and iv > 0 else None
        mos_pct = stock_data.get("mos_pct")
        mos_float = float(mos_pct) if mos_pct is not None else None

        gross_div_pct = float(stock_data.get("dividend_yield") or 0.0)
        net_div_pct = round(gross_div_pct * (1.0 - PH_DIVIDEND_TAX_RATE), 2)
        net_cash_per_10k = round(10_000.0 * (net_div_pct / 100.0), 2)
        spread_vs_bval_bps = round((net_div_pct - BENCHMARK_10Y_BVAL_PCT) * 100.0, 1)

        breakdown = stock_data.get("breakdown") if isinstance(stock_data.get("breakdown"), dict) else {}
        layers = breakdown.get("layers") if isinstance(breakdown.get("layers"), dict) else {}

        health_score = stock_data.get("health_score")
        if health_score is None and isinstance(layers.get("health"), dict):
            health_score = layers["health"].get("score")
        improvement_score = stock_data.get("improvement_score")
        if improvement_score is None and isinstance(layers.get("improvement"), dict):
            improvement_score = layers["improvement"].get("score")
        persistence_score = stock_data.get("persistence_score")
        if persistence_score is None and isinstance(layers.get("persistence"), dict):
            persistence_score = layers["persistence"].get("score")

        roe_pct = stock_data.get("roe")
        net_margin_pct = stock_data.get("net_margin")
        debt_to_equity = stock_data.get("debt_to_equity")
        if debt_to_equity is None:
            debt_to_equity = stock_data.get("de_ratio")

        is_illiquid = bool(stock_data.get("is_illiquid", False))
        is_bank = bool(stock_data.get("is_bank", False) or sector in ("Banks", "Financials") and ticker in ("BDO", "BPI", "MBT", "SECB", "CHIB", "PNB", "UBP", "EW", "RCB"))
        filter_passed = bool(stock_data.get("filter_passed", True))
        filter_reason = str(stock_data.get("filter_reason") or "").strip()
        net_income = stock_data.get("net_income")
        equity = stock_data.get("equity")
        total_debt = stock_data.get("total_debt")
        eps = stock_data.get("eps")
        mos_target = stock_data.get("mos_target_price")
        mos_target_float = float(mos_target) if mos_target is not None and float(mos_target) > 0 else None

        # Extract 3-Model Valuation Triangulation (DDM, EPS-PE, DCF)
        val_dict = stock_data.get("valuation") if isinstance(stock_data.get("valuation"), dict) else {}
        ddm_val = val_dict.get("ddm", {}).get("value") if isinstance(val_dict.get("ddm"), dict) else None
        pe_val = val_dict.get("eps_pe", {}).get("value") if isinstance(val_dict.get("eps_pe"), dict) else None
        dcf_val = val_dict.get("dcf", {}).get("value") if isinstance(val_dict.get("dcf"), dict) else None
        req_ret = stock_data.get("required_return")
        req_ret_pct = round(float(req_ret) * 100.0, 1) if req_ret is not None else None

        # Extract 3-Year EPS Trajectory & CAGRs
        eps_hist = stock_data.get("eps_3y") or stock_data.get("eps_5y") or []
        valid_eps = [float(e) for e in eps_hist if e is not None][:3]
        if len(valid_eps) >= 2:
            # Reverse from newest-first to chronological (oldest -> newest)
            chron_eps = list(reversed(valid_eps))
            eps_traj_str = " -> ".join(f"₱{v:.2f}" for v in chron_eps)
        elif eps is not None:
            eps_traj_str = f"₱{float(eps):.2f} (latest)"
        else:
            eps_traj_str = None

        rev_cagr = stock_data.get("revenue_cagr")
        div_cagr = stock_data.get("dividend_cagr_5y")
        fcf_yield = stock_data.get("fcf_yield")
        pe_ratio = stock_data.get("pe")
        pb_ratio = stock_data.get("pb")

        intel = PSE_COMPANY_INTEL.get(ticker, {})
        moat_desc = intel.get("moat", f"Established player sa {sector} sector ng Philippine Stock Exchange.")
        risk_desc = intel.get("risk", f"Bantayan: Macroeconomic cycles at quarterly earnings consistency sa {sector} sector.")

        bucket_tag, bucket_label = cls.classify_goal_bucket(
            score=score,
            mos_pct=mos_float,
            net_div_yield_pct=net_div_pct,
            debt_to_equity=debt_to_equity,
            is_illiquid=is_illiquid,
            is_bank=is_bank,
            filter_passed=filter_passed,
            net_income=net_income,
            equity=equity,
            raw_score=breakdown.get("raw_score"),
        )

        # ── 1. Verdict (Natural Taglish backed by Specific Moat + PSE Edge Facts) ──
        if bucket_tag == "PASSIVE_INCOME_CHAMPION":
            verdict = (
                f"Solid pang-passive income ang {name} ({ticker}): {moat_desc} "
                f"Nagbibigay ito ng {net_div_pct:.2f}% net dividend yield habang naka-discount pa ng {max(0.0, mos_float or 0.0):.1f}% sa Fair Value."
            )
        elif bucket_tag == "UNDERVALUED_BLUE_CHIP":
            verdict = (
                f"On-sale na higante ang {name} ({ticker}): {moat_desc} "
                f"Matatag ang fundamentals ({score:.1f}/100) at may {mos_float or 0.0:.1f}% Margin of Safety discount laban sa ₱{iv_float or price:,.2f} Fair Value nito."
            )
        elif bucket_tag == "QUALITY_COMPOUNDER":
            cagr_note = f" (+{float(rev_cagr):.1f}% Revenue CAGR)" if rev_cagr is not None and float(rev_cagr) > 0 else ""
            verdict = (
                f"Long-term compounder ang {name} ({ticker}): {moat_desc} "
                f"Consistent ang paglago ng kita{cagr_note} na may mataas na {score:.1f}/100 Quality Score."
            )
        else:
            if net_income is not None and net_income < 0:
                loss_b = cls._to_billions(net_income)
                verdict = (
                    f"Iwas muna sa {name} ({ticker}): {moat_desc} Base sa audited PSE Edge financials, may ₱{loss_b:,.2f} Billion "
                    f"net loss ito (EPS: ₱{float(eps or 0.0):.2f}) at bagsak sa safety filter ({filter_reason or f'Score: {score:.1f}/100'})."
                )
            elif not filter_passed and filter_reason:
                verdict = (
                    f"Iwas muna sa {name} ({ticker}): {moat_desc} Bagsak sa safety filter natin based on PSE Edge filings "
                    f"({filter_reason}; Quality Score: {score:.1f}/100)."
                )
            else:
                verdict = (
                    f"Iwas muna sa {name} ({ticker}): {moat_desc} Bagsak sa safety at valuation filter natin (Score: {score:.1f}/100). "
                    f"Mag-ingat sa hype hangga't hindi umaayos ang audited earnings at valuation."
                )

        # ── 2. Peso Value Test (With 3-Model Triangulation & Entry Price Zones) ──
        tri_parts = []
        if ddm_val is not None:
            tri_parts.append(f"DDM: ₱{float(ddm_val):,.2f}")
        if pe_val is not None:
            tri_parts.append(f"P/E Model: ₱{float(pe_val):,.2f}")
        if dcf_val is not None:
            tri_parts.append(f"DCF: ₱{float(dcf_val):,.2f}")
        tri_str = f" [Models: {' | '.join(tri_parts)}]" if tri_parts else ""
        target_str = f" Deep-Value Bargain Zone: ≤₱{mos_target_float:,.2f}." if mos_target_float else ""

        if iv_float and price > 0:
            peso_cost = round(price / iv_float, 2)
            if bucket_tag == "VALUE_OR_HYPE_TRAP":
                if mos_float is not None and mos_float > 0:
                    peso_value_test = (
                        f"Kahit mukhang mura sa papel (₱{peso_cost:.2f} per ₱1.00 of model value; Price: ₱{price:,.2f} vs. "
                        f"Model Value: ₱{iv_float:,.2f}), classic Value Trap risk ito dahil bagsak sa safety filter.{tri_str} "
                        f"Action: Avoid / Hintayin munang umayos ang balance sheet at kita."
                    )
                else:
                    peso_value_test = (
                        f"Overpriced at bagsak pa sa safety filter: nagbabayad ka ng ₱{peso_cost:.2f} for every ₱1.00 of value "
                        f"(Current Price: ₱{price:,.2f} vs. Fair Value: ₱{iv_float:,.2f}).{tri_str} Action: Avoid For Now."
                    )
            elif mos_float is not None and mos_float >= 5.0:
                peso_value_test = (
                    f"Nagbabayad ka lang ng ₱{peso_cost:.2f} for every ₱1.00 of true business value "
                    f"(Current Price: ₱{price:,.2f} vs. Blended Fair Value: ₱{iv_float:,.2f} — {mos_float:.1f}% discount).{tri_str} "
                    f"Action: Accumulate via Limit Order up to ₱{iv_float:,.2f}.{target_str}"
                )
            elif mos_float is not None and mos_float >= -5.0:
                peso_value_test = (
                    f"Sakto sa Fair Value: nagbabayad ka ng ₱{peso_cost:.2f} for every ₱1.00 of business value "
                    f"(Current Price: ₱{price:,.2f} vs. Fair Value: ₱{iv_float:,.2f}).{tri_str}{target_str}"
                )
            else:
                peso_value_test = (
                    f"Mas mahal na sa Fair Value ngayon: nagbabayad ka ng ₱{peso_cost:.2f} for every ₱1.00 of value "
                    f"(Current Price: ₱{price:,.2f} vs. Fair Value: ₱{iv_float:,.2f}).{tri_str} "
                    f"Action: Hold / Wait for pullback papalapit sa ₱{iv_float:,.2f} bago bumili."
                )
        elif net_income is not None and net_income < 0:
            peso_value_test = (
                f"Current Price is ₱{price:,.2f}, pero walang DCF/EPS Fair Value cushion dahil negatibo ang kita "
                f"(EPS: ₱{float(eps or 0.0):.2f}) — mataas ang panganib ng dilution o capital loss."
            )
        else:
            peso_value_test = (
                f"Current Market Price is ₱{price:,.2f}. Sinusukat base sa tibay ng kita at balance sheet."
            )

        # ── 3. Net Dividend per ₱10k ──────────────────────────
        div_cagr_note = (
            f" Lumago rin ang dibidendo nito ng +{float(div_cagr):.1f}%/year (5Y CAGR)."
            if div_cagr is not None and float(div_cagr) > 0
            else ""
        )
        if net_div_pct > 0:
            bank_mult = max(1.0, net_div_pct / TRADITIONAL_BANK_SAVINGS_RATE)
            net_dividend_per_10k = (
                f"Sa bawat ₱10,000 na investment, kikita ka ng ~₱{net_cash_per_10k:,.0f}/year in net cash dividends "
                f"({net_div_pct:.2f}% net after 10% tax; {gross_div_pct:.2f}% gross) — "
                f"halos {bank_mult:.0f}x na mas mataas kaysa sa 0.25% traditional bank savings account.{div_cagr_note}"
            )
        elif net_income is not None and net_income < 0:
            net_dividend_per_10k = (
                "₱0/year (0.00% dividend yield) — hindi makapagbigay ng cash dividend dahil nalulugi pa ang operasyon."
            )
        else:
            net_dividend_per_10k = (
                "₱0/year sa ngayon — ginagamit ng kumpanya ang profits pabalik sa expansion imbes na cash dividend."
            )

        # ── 4. Health (With 3Y EPS Trajectory, ROE, Debt & Specific Risk Catalyst) ──
        health_parts = [f"Quality Score: {score:.1f}/100 ({stock_data.get('category', 'Screened')})."]
        if eps_traj_str:
            health_parts.append(f"3Y Audited EPS Trend: {eps_traj_str}.")
        if roe_pct is not None:
            if roe_pct >= 0:
                health_parts.append(
                    f"Kumikita ng ₱{roe_pct:.1f} net profit bawat ₱100 capital (ROE)."
                )
            else:
                health_parts.append(
                    f"Nalulugi ng ₱{abs(roe_pct):.1f} sa bawat ₱100 na capital ({roe_pct:.1f}% ROE)."
                )
        elif net_income is not None and net_income < 0:
            loss_b = cls._to_billions(net_income)
            health_parts.append(f"Audited Net Loss: -₱{loss_b:,.2f} Billion.")

        if equity is not None and equity <= 0:
            eq_b = cls._to_billions(equity)
            debt_b = cls._to_billions(total_debt) if total_debt else 0.0
            health_parts.append(
                f"Capital Deficiency (Negative Shareholder Equity: -₱{eq_b:,.2f}B; Total Liabilities: ₱{debt_b:,.2f}B)."
            )
        elif debt_to_equity is not None:
            if is_bank:
                health_parts.append(
                    f"Universal bank structure (deposit-funded balance sheet; D/E: {debt_to_equity:.2f}x)."
                )
            elif debt_to_equity <= 0.8:
                health_parts.append(
                    f"Mababa at safe ang utang (₱{debt_to_equity * 100:.0f} debt per ₱100 equity)."
                )
            elif debt_to_equity <= 1.5:
                health_parts.append(
                    f"Manageable ang utang (D/E: {debt_to_equity:.2f}x)."
                )
            else:
                health_parts.append(
                    f"Mataas ang utang (₱{debt_to_equity * 100:.0f} debt per ₱100 equity — bantayan ang interest expense)."
                )
        health_parts.append(risk_desc)
        health_str = " ".join(health_parts)

        fact_card = FactCard(
            bucket_tag=bucket_tag,
            bucket_label=bucket_label,
            verdict=verdict,
            peso_value_test=peso_value_test,
            net_dividend_per_10k=net_dividend_per_10k,
            health=health_str,
        )

        seasoned = SeasonedNumbers(
            composite_score=round(score, 2),
            health_score=round(float(health_score), 2) if health_score is not None else None,
            improvement_score=round(float(improvement_score), 2) if improvement_score is not None else None,
            persistence_score=round(float(persistence_score), 2) if persistence_score is not None else None,
            confidence_pct=round(confidence * 100.0, 1),
            current_price_php=round(price, 2),
            intrinsic_value_php=round(iv_float, 2) if iv_float is not None else None,
            margin_of_safety_pct=round(mos_float, 2) if mos_float is not None else None,
            gross_dividend_yield_pct=round(gross_div_pct, 2),
            net_dividend_yield_pct=net_div_pct,
            net_annual_cash_per_10k_php=net_cash_per_10k,
            spread_vs_bval_bps=spread_vs_bval_bps,
            roe_pct=round(float(roe_pct), 2) if roe_pct is not None else None,
            net_margin_pct=round(float(net_margin_pct), 2) if net_margin_pct is not None else None,
            debt_to_equity=round(float(debt_to_equity), 2) if debt_to_equity is not None else None,
            mos_target_price_php=round(mos_target_float, 2) if mos_target_float is not None else None,
            ddm_value_php=round(float(ddm_val), 2) if ddm_val is not None else None,
            pe_value_php=round(float(pe_val), 2) if pe_val is not None else None,
            dcf_value_php=round(float(dcf_val), 2) if dcf_val is not None else None,
            eps_trajectory_str=eps_traj_str,
            revenue_cagr_pct=round(float(rev_cagr), 1) if rev_cagr is not None else None,
            dividend_cagr_pct=round(float(div_cagr), 1) if div_cagr is not None else None,
            fcf_yield_pct=round(float(fcf_yield), 2) if fcf_yield is not None else None,
            pe_ratio=round(float(pe_ratio), 2) if pe_ratio is not None else None,
            pb_ratio=round(float(pb_ratio), 2) if pb_ratio is not None else None,
            required_return_pct=req_ret_pct,
        )

        fc_dict = asdict(fact_card)
        # Keep backwards-compatible keys so existing callers/tests work seamlessly
        fc_dict["headline_verdict"] = fact_card.verdict
        fc_dict["piso_value_fact"] = fact_card.peso_value_test
        fc_dict["dividend_cash_fact"] = fact_card.net_dividend_per_10k
        fc_dict["business_safety_fact"] = fact_card.health

        return {
            "rank": stock_data.get("rank", 0),
            "ticker": ticker,
            "name": name,
            "sector": sector,
            "category": stock_data.get("category", "Screened"),
            "filter_passed": filter_passed,
            "filter_reason": filter_reason,
            "bucket_tag": bucket_tag,
            "bucket_label": bucket_label,
            "fact_card": fc_dict,
            "plain_facts": fc_dict,
            "seasoned_numbers": asdict(seasoned),
            "forensic_proof": asdict(seasoned),
        }

    @classmethod
    def compile_investment_menu(
        cls,
        ranked_stocks: List[Dict[str, Any]],
        goal_filter: Optional[str] = None,
        hype_check_ticker: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Compiles the complete Done-For-You Investment Menu grouped by investor goal buckets,
        plus an optional Hype Check lookup for any stock seen on Facebook groups.
        """
        all_compiled = [cls.compile_stock_option(s) for s in ranked_stocks]

        # Resolve optional FB Group Hype Check ticker
        hype_check_result = None
        if hype_check_ticker and hype_check_ticker.strip():
            target_t = hype_check_ticker.strip().upper()
            hype_check_result = next((c for c in all_compiled if c["ticker"] == target_t), None)

        # Filter main menu options by goal (prioritizing attractively valued picks ahead of overvalued/trap stocks)
        compiled_options = list(all_compiled)
        compiled_options.sort(
            key=lambda c: (
                c["bucket_tag"] != "VALUE_OR_HYPE_TRAP",
                (c["seasoned_numbers"].get("margin_of_safety_pct") or 0.0) > 0.0,
                float(c["seasoned_numbers"].get("composite_score") or 0.0),
            ),
            reverse=True,
        )
        if goal_filter and goal_filter != "all":
            filter_map = {
                "dividend": "PASSIVE_INCOME_CHAMPION",
                "value": "UNDERVALUED_BLUE_CHIP",
                "growth": "QUALITY_COMPOUNDER",
            }
            target_bucket = filter_map.get(goal_filter.lower())
            if target_bucket:
                filtered = [c for c in compiled_options if c["bucket_tag"] == target_bucket]
                if filtered:
                    compiled_options = filtered

        buckets = {
            "passive_income_champions": [
                c for c in all_compiled if c["bucket_tag"] == "PASSIVE_INCOME_CHAMPION"
            ],
            "undervalued_blue_chips": [
                c for c in all_compiled if c["bucket_tag"] == "UNDERVALUED_BLUE_CHIP"
            ],
            "quality_compounders": [
                c for c in all_compiled if c["bucket_tag"] == "QUALITY_COMPOUNDER"
            ],
            "avoid_traps": [
                c for c in all_compiled if c["bucket_tag"] == "VALUE_OR_HYPE_TRAP"
            ],
        }

        # Free Teaser Sample (Top #1 pick)
        teaser_sample = all_compiled[0] if all_compiled else None

        return {
            "goal_filter": goal_filter or "all",
            "hype_check_ticker": hype_check_ticker.strip().upper() if hype_check_ticker else None,
            "hype_check_result": hype_check_result,
            "teaser_sample": teaser_sample,
            "total_options": len(compiled_options),
            "options": compiled_options,
            "buckets": buckets,
            "pwyc_tiers": [
                {
                    "id": "starter",
                    "label": "Starter / Studyante Pass",
                    "suggested_php": 99.0,
                    "description": "Pang-nagsisimula pa lang. Covers our server & PSE data processing costs.",
                },
                {
                    "id": "community",
                    "label": "Fair Community Price (Recommended)",
                    "suggested_php": 249.0,
                    "description": "Standard Done-For-You Report price. Keeps the platform accessible for all Filipinos.",
                },
                {
                    "id": "supporter",
                    "label": "Seasoned / Pay-It-Forward",
                    "suggested_php": 499.0,
                    "description": "Para sa seasoned investors. Directly sponsors research access for 2 beginners.",
                },
            ],
        }
