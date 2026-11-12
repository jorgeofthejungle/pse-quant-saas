"""
pse_quant/reporting/generator.py — Done-For-You PDF Report Generator
Assembles the complete StockPilot PH Done-For-You Investment Dossier (A4 PDF) featuring:
  - Part 1: Curated "Take Your Pick" Fact Cards (Verdict, Peso Value Test, Net Dividend per 10k, Health + Seasoned Numbers)
  - Part 2: FB Group "Hype Check" Fact Cards (Why hyped/overvalued stocks fail the safety filter)
  - Part 3: Complete Seasoned Numbers Leaderboard Table
  - Part 4: Methodology & SEC Non-Advisory Notice
"""

from __future__ import annotations
from pathlib import Path
from typing import Any
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)

from pse_quant.reporting.styles import (
    PAGE_WIDTH,
    PAGE_HEIGHT,
    LEFT_MARGIN,
    RIGHT_MARGIN,
    TOP_MARGIN,
    BOTTOM_MARGIN,
    CONTENT_WIDTH,
    NAVY,
    GOLD_LIGHT,
    GREEN,
    GREEN_LIGHT,
    RED,
    RED_LIGHT,
    BLUE,
    BLUE_LIGHT,
    LIGHT_GREY,
    BORDER_GREY,
    DARK_GREY,
    WHITE,
    get_report_stylesheet,
)


def _sanitize_pdf_text(text: str) -> str:
    """Replaces Unicode symbols unsupported by standard PDF Type1 fonts (Helvetica)."""
    return (
        str(text)
        .replace("₱", "PHP ")
        .replace("≤", "&lt;= ")
        .replace("—", " - ")
        .replace("–", "-")
        .replace("•", "-")
    )


def _build_fact_card_box(compiled: dict[str, Any], styles: Any) -> KeepTogether:
    """Renders a single visual Fact Card + Seasoned Numbers strip as a bordered PDF table."""
    fc = compiled["fact_card"]
    sn = compiled["seasoned_numbers"]
    is_trap = compiled["bucket_tag"] == "VALUE_OR_HYPE_TRAP"

    header_bg = RED_LIGHT if is_trap else (GREEN_LIGHT if compiled["bucket_tag"] == "PASSIVE_INCOME_CHAMPION" else BLUE_LIGHT)
    badge_color = RED.hexval() if is_trap else (GREEN.hexval() if compiled["bucket_tag"] == "PASSIVE_INCOME_CHAMPION" else BLUE.hexval())
    border_color = RED if is_trap else BORDER_GREY

    verdict_txt = _sanitize_pdf_text(fc["verdict"])
    peso_txt = _sanitize_pdf_text(fc["peso_value_test"])
    div_txt = _sanitize_pdf_text(fc["net_dividend_per_10k"])
    health_txt = _sanitize_pdf_text(fc["health"])
    bucket_lbl = _sanitize_pdf_text(fc["bucket_label"])

    iv_str = f"PHP {sn['intrinsic_value_php']:,.2f}" if sn.get("intrinsic_value_php") else "N/A"
    mos_val = sn.get("margin_of_safety_pct")
    mos_str = f"{mos_val:+.1f}%" if mos_val is not None else "N/A"
    roe_str = f"{sn['roe_pct']:.1f}%" if sn.get("roe_pct") is not None else "N/A"
    de_str = f"{sn['debt_to_equity']:.2f}x" if sn.get("debt_to_equity") is not None else "N/A"
    sub_scores = ""
    h = sn.get("health_score")
    i = sn.get("improvement_score")
    p = sn.get("persistence_score")
    if h is not None and i is not None and p is not None:
        sub_scores = f" (H:{h:.0f} | I:{i:.0f} | P:{p:.0f})"

    header_row = [
        Paragraph(
            f"<b>{compiled['ticker']} - {_sanitize_pdf_text(compiled['name'])}</b> "
            f"<font color='#64748B'>[{_sanitize_pdf_text(compiled['sector'])}]</font>",
            styles["BodySmall"],
        ),
        Paragraph(
            f"<font color='{badge_color}'><b>{bucket_lbl}</b></font>",
            styles["BodySmall"],
        ),
    ]

    body_html = (
        f"<b>1. Verdict:</b> {verdict_txt}<br/>"
        f"<b>2. Peso Value Test:</b> {peso_txt}<br/>"
        f"<b>3. Net Dividend per PHP 10k:</b> {div_txt}<br/>"
        f"<b>4. Health:</b> {health_txt}"
    )

    seasoned_line1 = (
        f"<b>Seasoned Numbers:</b> "
        f"3-Layer Score: <b>{sn['composite_score']:.1f}/100</b>{sub_scores} &nbsp;|&nbsp; "
        f"Price: <b>PHP {sn['current_price_php']:,.2f}</b> vs. Fair Value: <b>{iv_str}</b> (MoS: <b>{mos_str}</b>) &nbsp;|&nbsp; "
        f"Net Div: <b>{sn['net_dividend_yield_pct']:.2f}%</b> &nbsp;|&nbsp; "
        f"ROE: <b>{roe_str}</b> &nbsp;|&nbsp; D/E: <b>{de_str}</b>"
    )

    extra_metrics = []
    if sn.get("ddm_value_php") is not None:
        extra_metrics.append(f"DDM: PHP {sn['ddm_value_php']:,.2f}")
    if sn.get("pe_value_php") is not None:
        extra_metrics.append(f"P/E Val: PHP {sn['pe_value_php']:,.2f}")
    if sn.get("dcf_value_php") is not None:
        extra_metrics.append(f"DCF: PHP {sn['dcf_value_php']:,.2f}")
    if sn.get("mos_target_price_php") is not None:
        extra_metrics.append(f"Bargain Entry (30% MoS): &lt;=PHP {sn['mos_target_price_php']:,.2f}")
    if sn.get("pe_ratio") is not None:
        extra_metrics.append(f"P/E: {sn['pe_ratio']:.1f}x")
    if sn.get("pb_ratio") is not None:
        extra_metrics.append(f"P/B: {sn['pb_ratio']:.2f}x")
    if sn.get("fcf_yield_pct") is not None:
        extra_metrics.append(f"FCF Yield: {sn['fcf_yield_pct']:.1f}%")

    if extra_metrics:
        seasoned_html = f"{seasoned_line1}<br/><font color='#475569'><b>Valuation &amp; Multiples:</b> {' &nbsp;|&nbsp; '.join(extra_metrics)}</font>"
    else:
        seasoned_html = seasoned_line1

    card_table = Table(
        [
            header_row,
            [Paragraph(body_html, styles["BodySmall"]), ""],
            [Paragraph(seasoned_html, styles["BodySmall"]), ""],
        ],
        colWidths=[CONTENT_WIDTH * 0.65, CONTENT_WIDTH * 0.35],
    )
    card_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), header_bg),
                ("BACKGROUND", (0, 1), (-1, 1), WHITE),
                ("BACKGROUND", (0, 2), (-1, 2), LIGHT_GREY),
                ("SPAN", (0, 1), (1, 1)),
                ("SPAN", (0, 2), (1, 2)),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 0.8, border_color),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, border_color),
                ("LINEBELOW", (0, 1), (-1, 1), 0.5, BORDER_GREY),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return KeepTogether([card_table, Spacer(1, 7)])


def generate_pdf_report(
    ranked_stocks: list[dict[str, Any]],
    output_path: str | Path,
    run_date: str | None = None,
    total_screened: int = 250,
    goal_filter: str | None = None,
    hype_check_ticker: str | None = None,
) -> Path:
    """
    Generates the A4 Done-For-You research PDF report.
    Returns the Path to the generated PDF.
    """
    from datetime import date
    from pse_quant.core.fact_compiler import DoneForYouFactCompiler

    if run_date is None:
        run_date = date.today().isoformat()
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
        leftMargin=LEFT_MARGIN,
        rightMargin=RIGHT_MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN,
    )

    styles = get_report_stylesheet()
    story = []

    goal_labels = {
        "all": "All-Weather Top Picks (Dividends + Value + Growth)",
        "dividend": "Option A Focus: Steady Cash Dividends",
        "value": "Option B Focus: Undervalued Blue Chips",
        "growth": "Option C Focus: Quality Growth Compounders",
    }
    goal_display = goal_labels.get((goal_filter or "all").lower(), goal_labels["all"])

    # ── 1. Header Banner ──────────────────────────────────────
    header_data = [
        [
            Paragraph("<b>StockPilot PH</b>", styles["ReportTitle"]),
            Paragraph(
                f"<b>Report Date:</b> {run_date}<br/>"
                f"<b>Focus:</b> {_sanitize_pdf_text(goal_display)}<br/>"
                f"<b>Source:</b> Official PSE Edge Audited Filings ({total_screened}+ Screened)",
                styles["BodySmall"],
            ),
        ]
    ]
    t_header = Table(header_data, colWidths=[CONTENT_WIDTH * 0.58, CONTENT_WIDTH * 0.42])
    t_header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(t_header)

    story.append(
        Paragraph(
            "Done-For-You Philippine Investment Dossier - Taglish Fact Cards, Valuation Triangulation & Execution Blueprint",
            styles["ReportSubtitle"],
        )
    )
    story.append(Spacer(1, 10))

    stocks_to_render = ranked_stocks or []
    compiled_all = [DoneForYouFactCompiler.compile_stock_option(s) for s in stocks_to_render]

    # Optional Requested Ticker Spotlight
    if hype_check_ticker and hype_check_ticker.strip():
        req_t = hype_check_ticker.strip().upper()
        req_match = next((c for c in compiled_all if c["ticker"] == req_t), None)
        if req_match:
            story.append(
                Paragraph(
                    f"Requested Stock Reality Check Spotlight: {req_t} ({_sanitize_pdf_text(req_match['name'])})",
                    styles["SectionHeader"],
                )
            )
            story.append(
                Paragraph(
                    "Narito ang kumpletong PSE Edge audit para sa stock ticker na pina-check mo:",
                    styles["BodySmall"],
                )
            )
            story.append(Spacer(1, 5))
            story.append(_build_fact_card_box(req_match, styles))
            story.append(Spacer(1, 4))

    top_picks = [c for c in compiled_all if c["bucket_tag"] != "VALUE_OR_HYPE_TRAP"]
    top_picks.sort(
        key=lambda c: (
            (c["seasoned_numbers"].get("margin_of_safety_pct") or 0.0) > 0.0,
            float(c["seasoned_numbers"].get("composite_score") or 0.0),
        ),
        reverse=True,
    )
    if goal_filter and goal_filter.lower() in ("dividend", "value", "growth"):
        f_map = {
            "dividend": "PASSIVE_INCOME_CHAMPION",
            "value": "UNDERVALUED_BLUE_CHIP",
            "growth": "QUALITY_COMPOUNDER",
        }
        tb = f_map[goal_filter.lower()]
        goal_matches = [c for c in top_picks if c["bucket_tag"] == tb]
        if goal_matches:
            others = [c for c in top_picks if c["bucket_tag"] != tb]
            top_picks = goal_matches + others

    trap_checks = [c for c in compiled_all if c["bucket_tag"] == "VALUE_OR_HYPE_TRAP"]
    trap_checks.sort(key=lambda c: (bool(c.get("filter_passed", True)), float(c["seasoned_numbers"].get("composite_score") or 0.0)))

    # ── Part 1: Curated "Take Your Pick" Fact Cards ───────────
    if top_picks:
        story.append(Paragraph("Part 1: Done-For-You Investment Menu ('Take Your Pick')", styles["SectionHeader"]))
        story.append(
            Paragraph(
                "Sagot sa tanong na 'Ano po maganda bilhin?': Pinili ng algorithm natin ang top PSE stocks base sa "
                "audited PSE Edge financial statements (3-Layer Health at 3-Model DCF/DDM/PE Fair Value). Bawat Fact Card ay may "
                "specific business moat, 3-year EPS trend, valuation triangulation, at key risk na dapat bantayan.",
                styles["BodySmall"],
            )
        )
        story.append(Spacer(1, 6))

        for comp in top_picks[:5]:
            story.append(_build_fact_card_box(comp, styles))

    # ── Part 2: Starter Capital Allocation & Limit-Order Action Blueprint ──
    actionable_picks = [
        c for c in top_picks
        if (c["seasoned_numbers"].get("margin_of_safety_pct") or 0.0) > 0.0
    ]
    actionable_picks.sort(
        key=lambda c: float(c["seasoned_numbers"].get("composite_score") or 0.0)
        + float(c["seasoned_numbers"].get("net_dividend_yield_pct") or 0.0) * 0.5,
        reverse=True,
    )
    actionable_picks = actionable_picks[:4]
    if not actionable_picks and top_picks:
        actionable_picks = top_picks[:4]

    if actionable_picks:
        story.append(
            Paragraph(
                "Part 2: Sample Capital Allocation & Limit-Order Execution Blueprint",
                styles["SectionHeader"],
            )
        )
        story.append(
            Paragraph(
                "Paano hatiin ang puhunan nang hindi talo sa broker fees o overpricing? Narito ang model allocation "
                "para sa PHP 20,000 at PHP 50,000 starter portfolio gamit ang Top 4 Actionable Picks:",
                styles["BodySmall"],
            )
        )
        story.append(Spacer(1, 6))

        n_picks = len(actionable_picks)
        weight_pct = round(100.0 / n_picks, 1)
        alloc_20k = round(20_000.0 / n_picks, 0)
        alloc_50k = round(50_000.0 / n_picks, 0)

        alloc_rows = [
            [
                Paragraph("<b>Ticker &amp; Role</b>", styles["BodySmall"]),
                Paragraph("<b>Weight</b>", styles["BodySmall"]),
                Paragraph("<b>PHP 20k Split</b>", styles["BodySmall"]),
                Paragraph("<b>PHP 50k Split</b>", styles["BodySmall"]),
                Paragraph("<b>Current Price</b>", styles["BodySmall"]),
                Paragraph("<b>Limit-Order Ceiling (Buy Up To)</b>", styles["BodySmall"]),
                Paragraph("<b>Est. Net Div/Yr (on PHP 50k)</b>", styles["BodySmall"]),
            ]
        ]

        total_net_div_50k = 0.0
        for pick in actionable_picks:
            sn = pick["seasoned_numbers"]
            cur_p = sn.get("current_price_php") or 0.0
            iv_p = sn.get("intrinsic_value_php") or cur_p
            buy_ceiling = max(cur_p, iv_p) if (sn.get("margin_of_safety_pct") or 0.0) >= 0 else iv_p
            bargain_p = sn.get("mos_target_price_php")
            ceiling_str = f"<b>&lt;=PHP {buy_ceiling:,.2f}</b>"
            if bargain_p:
                ceiling_str += f"<br/><font color='#64748B'>(Bargain: PHP {bargain_p:,.2f})</font>"

            net_y = sn.get("net_dividend_yield_pct") or 0.0
            est_div_php = round(alloc_50k * (net_y / 100.0), 0)
            total_net_div_50k += est_div_php

            alloc_rows.append(
                [
                    Paragraph(
                        f"<b>{pick['ticker']}</b><br/><font color='#64748B'>{_sanitize_pdf_text(pick['bucket_label'])}</font>",
                        styles["BodySmall"],
                    ),
                    Paragraph(f"{weight_pct:.0f}%", styles["BodySmall"]),
                    Paragraph(f"PHP {alloc_20k:,.0f}", styles["BodySmall"]),
                    Paragraph(f"PHP {alloc_50k:,.0f}", styles["BodySmall"]),
                    Paragraph(f"PHP {cur_p:,.2f}", styles["BodySmall"]),
                    Paragraph(ceiling_str, styles["BodySmall"]),
                    Paragraph(
                        f"<font color='#065F46'><b>PHP {est_div_php:,.0f}/yr</b> ({net_y:.2f}%)</font>",
                        styles["BodySmall"],
                    ),
                ]
            )

        bank_50k_div = round(50_000.0 * (0.25 / 100.0) * 0.80, 0)  # 0.25% gross less 20% bank interest tax = PHP 100/yr
        alloc_rows.append(
            [
                Paragraph("<b>TOTAL PORTFOLIO</b>", styles["BodySmall"]),
                Paragraph("<b>100%</b>", styles["BodySmall"]),
                Paragraph("<b>PHP 20,000</b>", styles["BodySmall"]),
                Paragraph("<b>PHP 50,000</b>", styles["BodySmall"]),
                Paragraph("-", styles["BodySmall"]),
                Paragraph("<b>Use Limit Orders Only</b>", styles["BodySmall"]),
                Paragraph(
                    f"<font color='#065F46'><b>~PHP {total_net_div_50k:,.0f}/yr</b></font><br/>"
                    f"<font color='#64748B'>(vs. PHP {bank_50k_div:,.0f}/yr sa Bank)</font>",
                    styles["BodySmall"],
                ),
            ]
        )

        t_alloc = Table(
            alloc_rows,
            colWidths=[
                CONTENT_WIDTH * 0.21,
                CONTENT_WIDTH * 0.09,
                CONTENT_WIDTH * 0.12,
                CONTENT_WIDTH * 0.12,
                CONTENT_WIDTH * 0.12,
                CONTENT_WIDTH * 0.18,
                CONTENT_WIDTH * 0.16,
            ],
        )
        t_alloc.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GREY),
                    ("BACKGROUND", (0, -1), (-1, -1), GREEN_LIGHT),
                    ("LINEBELOW", (0, 0), (-1, 0), 1.2, NAVY),
                    ("LINEBELOW", (0, 1), (-1, -2), 0.5, BORDER_GREY),
                    ("LINEABOVE", (0, -1), (-1, -1), 1.0, GREEN),
                    ("BOX", (0, 0), (-1, -1), 0.5, BORDER_GREY),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(t_alloc)
        story.append(Spacer(1, 6))

        playbook_html = (
            "<b>Seasoned Investor Execution Playbook (COL Financial / FirstMetroSec / BDO Sec / DragonFi):</b><br/>"
            "1. <b>The PHP 8,000 Broker Fee Rule:</b> May PHP 20 minimum commission (o 0.25% kung alin ang mas mataas) sa PSE brokers. "
            "Kapag bumili ka ng PHP 1,000 lang, talo ka agad ng ~2.1% sa fees. Mag-ipon ng at least <b>PHP 5,000 to PHP 8,000 per buy order</b> para sulit ang fee (~0.295% total friction).<br/>"
            "2. <b>Never Use Market Orders:</b> Laging gumamit ng <b>Limit Order</b> at huwag lumagpas sa <i>Limit-Order Ceiling (Fair Value)</i> sa table sa itaas.<br/>"
            "3. <b>Tranche Buying (Peso-Cost Averaging on Value):</b> Hatiin sa 2 tranches ang pagbili - 50% sa Current Price (kung undervalued) at 50% naka-abang malapit sa <i>Bargain Entry Zone</i>."
        )
        t_playbook = Table([[Paragraph(playbook_html, styles["BodySmall"])]], colWidths=[CONTENT_WIDTH])
        t_playbook.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), BLUE_LIGHT),
                    ("BOX", (0, 0), (-1, -1), 0.8, BLUE),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(t_playbook)
        story.append(Spacer(1, 12))

    # ── Part 3: Stock Reality Check (PSE Edge Safety Audit) ───
    if trap_checks:
        story.append(Paragraph("Part 3: Stock Reality Check (PSE Edge Safety & Red-Flag Audit)", styles["SectionHeader"]))
        story.append(
            Paragraph(
                "Bago bumili ng stock na narinig sa forums o social media, tingnan muna ang audited PSE Edge financials. "
                "Narito ang Fact Card ng mga real PSE stocks na kasalukuyang bagsak sa ating safety o valuation filter:",
                styles["BodySmall"],
            )
        )
        story.append(Spacer(1, 6))

        for trap in trap_checks[:3]:
            story.append(_build_fact_card_box(trap, styles))

    # ── Part 4: Seasoned Numbers Leaderboard Table ────────────
    story.append(Paragraph("Part 4: Complete 24-Stock PSE Edge Audit & Valuation Leaderboard", styles["SectionHeader"]))
    story.append(
        Paragraph(
            "Complete side-by-side comparison of 3-Layer Fundamental Scores, Current Prices, Intrinsic Fair Values, and Margin of Safety.",
            styles["BodySmall"],
        )
    )
    story.append(Spacer(1, 6))

    table_rows = [
        [
            Paragraph("<b>Rank</b>", styles["BodySmall"]),
            Paragraph("<b>Ticker</b>", styles["BodySmall"]),
            Paragraph("<b>Sector</b>", styles["BodySmall"]),
            Paragraph("<b>Score</b>", styles["BodySmall"]),
            Paragraph("<b>Fact Card Bucket</b>", styles["BodySmall"]),
            Paragraph("<b>Price</b>", styles["BodySmall"]),
            Paragraph("<b>Fair Value</b>", styles["BodySmall"]),
            Paragraph("<b>Margin of Safety</b>", styles["BodySmall"]),
        ]
    ]

    if not compiled_all:
        table_rows.append(
            [
                Paragraph("-", styles["BodySmall"]),
                Paragraph("<i>None</i>", styles["BodySmall"]),
                Paragraph("<i>No qualifying equities</i>", styles["BodySmall"]),
                Paragraph("N/A", styles["BodySmall"]),
                Paragraph("Watchlist", styles["BodySmall"]),
                Paragraph("N/A", styles["BodySmall"]),
                Paragraph("N/A", styles["BodySmall"]),
                Paragraph("N/A", styles["BodySmall"]),
            ]
        )
    else:
        for comp in compiled_all[:25]:
            sn = comp["seasoned_numbers"]
            price = sn.get("current_price_php")
            price_str = f"PHP {price:,.2f}" if price is not None else "N/A"
            iv = sn.get("intrinsic_value_php")
            iv_str = f"PHP {iv:,.2f}" if iv is not None else "N/A"
            mos = sn.get("margin_of_safety_pct")
            if mos is not None:
                mos_str = f"+{mos:.1f}%" if mos > 0 else f"{mos:.1f}%"
                mos_color = GREEN if mos > 0 else RED
            else:
                mos_str = "N/A"
                mos_color = DARK_GREY

            score = sn.get("composite_score")
            score_str = f"<b>{score:.1f}</b>" if score is not None else "N/A"
            rank_val = comp.get("rank")
            rank_str = f"#{rank_val}" if rank_val is not None else "-"
            ticker_str = comp.get("ticker", "UNKNOWN")
            sector_str = str(comp.get("sector", "General"))[:16]
            bucket_str = _sanitize_pdf_text(comp.get("bucket_label", "Screened"))

            table_rows.append(
                [
                    Paragraph(rank_str, styles["BodySmall"]),
                    Paragraph(f"<b>{ticker_str}</b>", styles["BodySmall"]),
                    Paragraph(sector_str, styles["BodySmall"]),
                    Paragraph(score_str, styles["BodySmall"]),
                    Paragraph(bucket_str, styles["BodySmall"]),
                    Paragraph(price_str, styles["BodySmall"]),
                    Paragraph(iv_str, styles["BodySmall"]),
                    Paragraph(f"<font color='{mos_color.hexval()}'><b>{mos_str}</b></font>", styles["BodySmall"]),
                ]
            )

    col_widths = [
        CONTENT_WIDTH * 0.07,  # Rank
        CONTENT_WIDTH * 0.10,  # Ticker
        CONTENT_WIDTH * 0.13,  # Sector
        CONTENT_WIDTH * 0.08,  # Score
        CONTENT_WIDTH * 0.24,  # Bucket
        CONTENT_WIDTH * 0.13,  # Price
        CONTENT_WIDTH * 0.13,  # Fair Value
        CONTENT_WIDTH * 0.12,  # MoS
    ]
    t_rankings = Table(table_rows, colWidths=col_widths)
    t_rankings.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GREY),
                ("LINEBELOW", (0, 0), (-1, 0), 1.5, NAVY),
                ("LINEBELOW", (0, 1), (-1, -1), 0.5, BORDER_GREY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(t_rankings)
    story.append(Spacer(1, 14))

    # ── Part 5: Methodology & Compliance Notice ───────────────
    story.append(
        KeepTogether(
            [
                Paragraph("Part 5: Methodology & Non-Advisory Notice", styles["SectionHeader"]),
                Paragraph(
                    "<b>How the Algorithm Works:</b> StockPilot PH audits listed Philippine equities across 3 deterministic layers: "
                    "(1) Financial Health (ROE, net profit margin, debt-to-equity safety, free cash flow), "
                    "(2) Improvement (3-year YoY earnings and revenue trajectory), and "
                    "(3) Persistence (multi-year consistency of growth).<br/><br/>"
                    "<b>Peso Value Test & Net Dividend Math:</b> Fair Value is computed using Discounted Cash Flow (DCF), "
                    "Dividend Discount Models (DDM), and normalized P/E multiples benchmarked against the Philippine 10-Year BVAL bond yield. "
                    "Net Dividend per PHP 10k deducts the mandatory 10% final withholding tax and compares net cash payout against "
                    "traditional 0.25% bank savings accounts. "
                    "<b>All figures are mathematical computations for educational and research purposes only</b> and do not constitute "
                    "solicitation or personalized investment advice.",
                    styles["DisclaimerText"],
                ),
            ]
        )
    )

    doc.build(story)
    return out_path
