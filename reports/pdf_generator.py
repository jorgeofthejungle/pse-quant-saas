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
from datetime import datetime
import os

from reports.pdf_styles import (
    build_styles, score_color, score_bg, grade, grade_label, mos_signal,
    GOLD, LEFT_MARGIN, RIGHT_MARGIN, TOP_MARGIN, BOTTOM_MARGIN,
    CONTENT_WIDTH,
)
from reports.pdf_cover_page import build_cover_page, build_disclaimer_page
from reports.pdf_rankings_table import build_rankings_table, generate_overall_assessment
from reports.pdf_stock_detail_page import build_stock_detail
from reports.pdf_sentiment import (
    build_sentiment_panel, build_news_overview_section,
    SENTIMENT_COLORS, SENTIMENT_BGS,
)

__all__ = [
    'generate_report',
    'build_styles', 'build_cover_page', 'build_disclaimer_page',
    'build_rankings_table', 'generate_overall_assessment',
    'build_stock_detail',
    'build_sentiment_panel', 'build_news_overview_section',
    'score_color', 'score_bg', 'grade', 'grade_label', 'mos_signal',
    'SENTIMENT_COLORS', 'SENTIMENT_BGS',
]


def generate_report(
    portfolio_type:        str,
    ranked_stocks:         list,
    output_path:           str,
    total_stocks_screened: int = 0,
):
    names = {
        'pure_dividend':   'PURE DIVIDEND',
        'dividend_growth': 'DIVIDEND GROWTH',
        'value':           'VALUE',
    }
    portfolio_name = names.get(portfolio_type, 'PORTFOLIO')
    run_date       = datetime.now().strftime('%B %d, %Y')
    eligible       = len(ranked_stocks)

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=LEFT_MARGIN,
        rightMargin=RIGHT_MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN,
    )

    styles   = build_styles()
    elements = []

    elements += build_cover_page(
        styles, portfolio_type, portfolio_name,
        run_date, total_stocks_screened, eligible
    )
    elements += build_rankings_table(styles, ranked_stocks, portfolio_type)
    elements += build_news_overview_section(ranked_stocks)
    elements.append(Spacer(1, 6 * mm))
    elements.append(PageBreak())
    elements.append(Paragraph(
        'DETAILED STOCK ANALYSIS - TOP 10',
        styles['SectionHeader']
    ))
    elements.append(HRFlowable(
        width=CONTENT_WIDTH, thickness=2,
        color=GOLD, spaceAfter=8
    ))

    for i, stock in enumerate(ranked_stocks[:10]):
        if i > 0:
            elements.append(PageBreak())
        elements += build_stock_detail(styles, stock, i + 1, portfolio_type)

    elements += build_disclaimer_page(styles)

    doc.build(elements)
    print(f"Report saved: {output_path}")
    return output_path
