# ============================================================
# pdf_portfolio_sections.py — Multi-section layout for unified PDF
# PSE Quant SaaS — Phase 11 (Task 12)
# ============================================================
# Builds section headers and dividers for the three portfolio
# sections in the unified StockPilot PH Rankings PDF.
# ============================================================

from reportlab.platypus import Paragraph, Spacer, HRFlowable, KeepTogether
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors as rl_colors


# Section display information keyed by portfolio_type
SECTION_INFO = {
    'dividend': {
        'title':    'Dividend Portfolio',
        'subtitle': 'Stocks ranked for yield, dividend consistency, and income reliability',
        'color':    '#1a5276',
    },
    'value': {
        'title':    'Value Portfolio',
        'subtitle': 'Stocks ranked for undervaluation and fundamental quality',
        'color':    '#7d3c98',
    },
    'unified': {
        'title':    'Unified Rankings',
        'subtitle': 'All PSE stocks ranked by combined fundamental score',
        'color':    '#2c3e50',
    },
}


def build_section_header(portfolio_type: str) -> list:
    """
    Builds a list of flowables for a portfolio section header.
    Includes title, subtitle, and a coloured rule.
    """
    info = SECTION_INFO.get(portfolio_type, {
        'title':    portfolio_type.replace('_', ' ').title(),
        'subtitle': '',
        'color':    '#2c3e50',
    })

    style_title = ParagraphStyle(
        'SectionTitle',
        fontName='Helvetica-Bold',
        fontSize=16,
        textColor=rl_colors.HexColor(info['color']),
        spaceAfter=4,
    )
    style_sub = ParagraphStyle(
        'SectionSub',
        fontName='Helvetica',
        fontSize=10,
        textColor=rl_colors.HexColor('#566573'),
        spaceAfter=8,
    )

    return [
        KeepTogether([
            Spacer(1, 12),
            Paragraph(info['title'], style_title),
            Paragraph(info['subtitle'], style_sub),
            HRFlowable(
                width='100%',
                thickness=1,
                color=rl_colors.HexColor(info['color']),
            ),
            Spacer(1, 8),
        ]),
    ]
