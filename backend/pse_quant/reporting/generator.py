"""
pse_quant/reporting/generator.py — PDF Report Generator
Assembles the complete StockPilot PH Rankings research report (A4 PDF).
"""

from __future__ import annotations
from pathlib import Path
from typing import Any
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
)
from reportlab.lib import colors

from pse_quant.reporting.styles import (
    PAGE_WIDTH,
    PAGE_HEIGHT,
    LEFT_MARGIN,
    RIGHT_MARGIN,
    TOP_MARGIN,
    BOTTOM_MARGIN,
    CONTENT_WIDTH,
    NAVY,
    GOLD,
    GREEN,
    RED,
    BLUE,
    LIGHT_GREY,
    BORDER_GREY,
    DARK_GREY,
    WHITE,
    DEFAULT_FONT,
    DEFAULT_BOLD,
    get_report_stylesheet,
)


def generate_pdf_report(
    ranked_stocks: list[dict[str, Any]],
    output_path: str | Path,
    run_date: str | None = None,
    total_screened: int = 250,
) -> Path:
    """
    Generates the A4 research PDF report.
    Returns the Path to the generated PDF.
    """
    from datetime import date
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

    # ── 1. Header Banner ──────────────────────────────────────
    header_data = [
        [
            Paragraph("<b>StockPilot PH</b>", styles["ReportTitle"]),
            Paragraph(f"<b>Run Date:</b> {run_date}<br/><b>Universe:</b> {total_screened} stocks screened", styles["BodySmall"]),
        ]
    ]
    t_header = Table(header_data, colWidths=[CONTENT_WIDTH * 0.70, CONTENT_WIDTH * 0.30])
    t_header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(t_header)

    story.append(Paragraph(
        "Deterministic Multi-Factor Philippine Equity Fundamental Rankings & Valuation Estimates",
        styles["ReportSubtitle"],
    ))
    story.append(Spacer(1, 14))

    # ── 2. Top Rankings Table ─────────────────────────────────
    story.append(Paragraph("Rankings Leaderboard", styles["SectionHeader"]))
    story.append(Paragraph(
        "Equities qualifying on 3 fundamental layers (Health, Improvement, Persistence) and scoring above the dynamic threshold.",
        styles["BodySmall"],
    ))
    story.append(Spacer(1, 8))

    table_rows = [
        [
            Paragraph("<b>Rank</b>", styles["BodySmall"]),
            Paragraph("<b>Ticker</b>", styles["BodySmall"]),
            Paragraph("<b>Sector</b>", styles["BodySmall"]),
            Paragraph("<b>Score</b>", styles["BodySmall"]),
            Paragraph("<b>Quality Band</b>", styles["BodySmall"]),
            Paragraph("<b>Current Price</b>", styles["BodySmall"]),
            Paragraph("<b>Intrinsic Value</b>", styles["BodySmall"]),
            Paragraph("<b>Margin of Safety</b>", styles["BodySmall"]),
        ]
    ]

    stocks_to_render = ranked_stocks or []
    if not stocks_to_render:
        table_rows.append([
            Paragraph("-", styles["BodySmall"]),
            Paragraph("<i>None</i>", styles["BodySmall"]),
            Paragraph("<i>No qualifying equities</i>", styles["BodySmall"]),
            Paragraph("N/A", styles["BodySmall"]),
            Paragraph("Watchlist", styles["BodySmall"]),
            Paragraph("N/A", styles["BodySmall"]),
            Paragraph("N/A", styles["BodySmall"]),
            Paragraph("N/A", styles["BodySmall"]),
        ])
    else:
        for stock in stocks_to_render[:20]:
            price = stock.get("current_price")
            price_str = f"PHP {price:,.2f}" if price is not None else "N/A"
            iv = stock.get("intrinsic_value")
            iv_str = f"PHP {iv:,.2f}" if iv is not None else "N/A"
            mos = stock.get("mos_pct")
            if mos is not None:
                mos_str = f"+{mos:.1f}%" if mos > 0 else f"{mos:.1f}%"
                mos_color = GREEN if mos > 0 else RED
            else:
                mos_str = "N/A"
                mos_color = DARK_GREY

            score = stock.get("score")
            score_str = f"<b>{score:.1f}</b>" if score is not None else "N/A"
            rank_val = stock.get("rank")
            rank_str = f"#{rank_val}" if rank_val is not None else "-"
            ticker_str = stock.get("ticker", "UNKNOWN")
            sector_str = str(stock.get("sector", "General"))[:14]
            category_str = stock.get("category", "Watchlist")

            table_rows.append([
                Paragraph(rank_str, styles["BodySmall"]),
                Paragraph(f"<b>{ticker_str}</b>", styles["BodySmall"]),
                Paragraph(sector_str, styles["BodySmall"]),
                Paragraph(score_str, styles["BodySmall"]),
                Paragraph(category_str, styles["BodySmall"]),
                Paragraph(price_str, styles["BodySmall"]),
                Paragraph(iv_str, styles["BodySmall"]),
                Paragraph(f"<font color='{mos_color.hexval()}'><b>{mos_str}</b></font>", styles["BodySmall"]),
            ])

    col_widths = [
        CONTENT_WIDTH * 0.08,  # Rank
        CONTENT_WIDTH * 0.12,  # Ticker
        CONTENT_WIDTH * 0.18,  # Sector
        CONTENT_WIDTH * 0.10,  # Score
        CONTENT_WIDTH * 0.18,  # Quality Band
        CONTENT_WIDTH * 0.11,  # Price
        CONTENT_WIDTH * 0.11,  # IV
        CONTENT_WIDTH * 0.12,  # MoS
    ]
    t_rankings = Table(table_rows, colWidths=col_widths)
    t_rankings.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GREY),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, NAVY),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, BORDER_GREY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_rankings)
    story.append(Spacer(1, 16))

    # ── 3. Methodology & Compliance Notice ─────────────────────
    story.append(KeepTogether([
        Paragraph("Methodology & Non-Advisory Notice", styles["SectionHeader"]),
        Paragraph(
            "<b>Scoring Framework:</b> StockPilot PH scores listed equities using a 3-layer deterministic model: "
            "(1) Financial Health (solvency, efficiency, leverage), (2) Fundamental Improvement (3-year recency-weighted deltas), "
            "and (3) Persistence (consistency of earnings and revenue streaks). Scoring groups are sector-adjusted for Banks, REITs, "
            "Conglomerates, Property, Mining, and Industrials.<br/><br/>"
            "<b>Valuation & Margin of Safety:</b> Intrinsic value is mathematically modeled using Discounted Cash Flow (DCF), "
            "Dividend Discount Models (DDM), and normalised earnings multiples (EPS x PE), discounted by risk-adjusted rates reflecting "
            "the Philippine 10-Year Treasury bond plus country, size, and sector risk premiums. "
            "<b>All figures are mathematical computations for research and educational purposes only.</b> "
            "They do not constitute investment advice, solicitations, or buy/sell recommendations.",
            styles["DisclaimerText"],
        ),
    ]))

    doc.build(story)
    return out_path
