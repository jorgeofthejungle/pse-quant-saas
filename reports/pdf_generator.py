# ============================================================
# pdf_generator.py — PUBLIC FACADE (re-exports all sub-modules)
# PSE Quant SaaS — Phase 2
# ============================================================
# Sub-modules:
#   pdf_styles.py            — colours, page settings, style helpers
#   pdf_cover_page.py        — build_cover_page(), build_disclaimer_page()
#   pdf_rankings_table.py    — build_rankings_table(), generate_overall_assessment()
#   pdf_stock_detail_page.py — build_stock_detail()
#   pdf_sentiment.py         — build_sentiment_panel(), build_news_overview_section()
# ============================================================

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, PageBreak
)
from reportlab.platypus.flowables import CondPageBreak
from reportlab.pdfgen import canvas as _canvas_mod
from datetime import datetime
import os

from reports.pdf_styles import (
    build_styles, score_color, score_bg, grade, grade_label, mos_signal,
    NAVY, GOLD, DARK_GREY, WHITE,
    LEFT_MARGIN, RIGHT_MARGIN, TOP_MARGIN, BOTTOM_MARGIN,
    CONTENT_WIDTH, draw_bar_icon,
)
from reports.pdf_cover_page import build_cover_page, build_disclaimer_page
from reports.pdf_rankings_table import build_rankings_table, generate_overall_assessment
from reports.pdf_stock_detail_page import build_stock_detail
from reports.pdf_portfolio_sections import build_section_header

PAGE_W, PAGE_H = A4


def _draw_page_frame(canv, doc):
    """Draws the branded header bar and footer on every page."""
    canv.saveState()

    # ── Top header bar ───────────────────────────────────────
    bar_h = 8 * mm
    canv.setFillColor(NAVY)
    canv.rect(0, PAGE_H - bar_h, PAGE_W, bar_h, fill=1, stroke=0)

    # Bar-chart icon (always drawn — no image file needed)
    icon_size = 5.5 * mm
    icon_x    = LEFT_MARGIN
    icon_y    = PAGE_H - bar_h + (bar_h - icon_size) / 2
    draw_bar_icon(canv, icon_x, icon_y, icon_size)
    text_x = icon_x + icon_size + 2.5 * mm

    # "Stockpilot" white text
    canv.setFillColor(WHITE)
    canv.setFont('Helvetica-Bold', 8)
    canv.drawString(text_x, PAGE_H - bar_h + 2.2 * mm, 'Stockpilot')
    # "PHILIPPINES" gold text
    name_w = canv.stringWidth('Stockpilot', 'Helvetica-Bold', 8)
    canv.setFillColor(GOLD)
    canv.setFont('Helvetica-Bold', 6)
    canv.drawString(text_x + name_w + 2 * mm, PAGE_H - bar_h + 2.8 * mm, 'PHILIPPINES')

    # Page number on the right
    canv.setFillColor(WHITE)
    canv.setFont('Helvetica', 7)
    page_str = f'Page {doc.page}'
    canv.drawRightString(PAGE_W - RIGHT_MARGIN, PAGE_H - bar_h + 2.5 * mm, page_str)

    # ── Gold accent line just below header ───────────────────
    canv.setStrokeColor(GOLD)
    canv.setLineWidth(1.5)
    canv.line(0, PAGE_H - bar_h, PAGE_W, PAGE_H - bar_h)

    # ── Footer ───────────────────────────────────────────────
    footer_y = 6 * mm
    canv.setStrokeColor(GOLD)
    canv.setLineWidth(0.5)
    canv.line(LEFT_MARGIN, footer_y, PAGE_W - RIGHT_MARGIN, footer_y)

    canv.setFillColor(DARK_GREY)
    canv.setFont('Helvetica-Oblique', 6.5)
    canv.drawCentredString(
        PAGE_W / 2, footer_y - 3.5 * mm,
        'For Research and Educational Purposes Only. Not Investment Advice. '
        'Data sourced from PSE Edge. Powered by Stockpilot Philippines.'
    )

    canv.restoreState()

__all__ = [
    'generate_report',
    'build_styles', 'build_cover_page', 'build_disclaimer_page',
    'build_rankings_table', 'generate_overall_assessment',
    'build_stock_detail',
    'score_color', 'score_bg', 'grade', 'grade_label', 'mos_signal',
]


def generate_report(
    ranked_sections:       object,
    output_path:           str,
    total_stocks_screened: int = 0,
    # Legacy positional arg support: old callers passed portfolio_type as 1st arg
    # and ranked_stocks as 2nd arg. Detect this via type check below.
    portfolio_type:        str = None,
):
    """
    Generate the unified StockPilot PH Rankings PDF.

    New call style (Task 12):
        generate_report(ranked_sections, output_path, total_stocks_screened)
        ranked_sections — dict: {'pure_dividend': [...], 'dividend_growth': [...], 'value': [...]}

    Legacy call style (backward compatible):
        generate_report(portfolio_type, ranked_stocks, output_path, total_stocks_screened)
        If ranked_sections is a str, treat as old-style single-section call.
        If ranked_sections is a list, treat as old-style with portfolio_type='unified'.
    """
    # ── Backward compatibility shim ──────────────────────────
    if isinstance(ranked_sections, str):
        # Called as generate_report(portfolio_type, ranked_stocks, output_path, ...)
        # ranked_sections holds portfolio_type, output_path holds ranked_stocks
        _pt     = ranked_sections
        _stocks = output_path
        _path   = total_stocks_screened
        _total  = portfolio_type or 0
        ranked_sections = {_pt: _stocks}
        output_path = _path
        total_stocks_screened = _total if isinstance(_total, int) else 0
    elif isinstance(ranked_sections, list):
        # Called as generate_report(ranked_stocks_list, output_path, total, ...)
        ranked_sections = {'unified': ranked_sections}

    names = {
        'pure_dividend':   'PURE DIVIDEND',
        'dividend_growth': 'DIVIDEND GROWTH',
        'value':           'VALUE',
        'unified':         'UNIFIED STOCK RANKINGS',
    }
    run_date = datetime.now().strftime('%B %d, %Y')

    # Determine cover-page portfolio type and name
    section_keys = list(ranked_sections.keys())
    if len(section_keys) == 1:
        cover_pt   = section_keys[0]
        cover_name = names.get(cover_pt, 'PORTFOLIO')
    else:
        cover_pt   = 'unified'
        cover_name = 'STOCKPILOT PH RANKINGS'

    total_eligible = sum(len(v) for v in ranked_sections.values())

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=LEFT_MARGIN,
        rightMargin=RIGHT_MARGIN,
        topMargin=TOP_MARGIN + 8 * mm,
        bottomMargin=BOTTOM_MARGIN + 6 * mm,
    )

    styles   = build_styles()
    elements = []

    elements += build_cover_page(
        styles, cover_pt, cover_name,
        run_date, total_stocks_screened, total_eligible,
    )

    # ── Ranked tables — one per section ──────────────────────
    section_order = ['pure_dividend', 'dividend_growth', 'value']
    ordered_sections = [k for k in section_order if k in ranked_sections]
    ordered_sections += [k for k in section_keys if k not in section_order]

    for pt in ordered_sections:
        stocks = ranked_sections[pt]
        if not stocks:
            continue
        elements += build_section_header(pt)
        elements += build_rankings_table(styles, stocks, pt)
        elements.append(Spacer(1, 6 * mm))

    elements.append(PageBreak())

    # ── Detailed stock pages — one per section ────────────────
    for pt in ordered_sections:
        stocks = ranked_sections[pt]
        if not stocks:
            continue
        elements += build_section_header(pt)
        elements.append(Paragraph(
            f'DETAILED STOCK ANALYSIS — ALL {len(stocks)} QUALIFYING STOCKS',
            styles['SectionHeader']
        ))
        elements.append(HRFlowable(
            width=CONTENT_WIDTH, thickness=2,
            color=GOLD, spaceAfter=8,
        ))
        for i, stock in enumerate(stocks):
            if i > 0:
                elements.append(CondPageBreak(180 * mm))
            elements += build_stock_detail(styles, stock, i + 1, pt)

    elements += build_disclaimer_page(styles)

    doc.build(elements, onFirstPage=_draw_page_frame, onLaterPages=_draw_page_frame)
    print(f"Report saved: {output_path}")
    return output_path
