# ============================================================
# pdf_styles.py — Color Palette, Page Settings, Style Helpers
# PSE Quant SaaS — reports sub-module
# ============================================================

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# ── Colour Palette ──────────────────────────────────────────
NAVY        = colors.HexColor('#1B4B6B')
NAVY_LIGHT  = colors.HexColor('#2C6A8F')
GOLD        = colors.HexColor('#4CAF7D')
GOLD_LIGHT  = colors.HexColor('#E8F8F0')
GREEN       = colors.HexColor('#27AE60')
GREEN_LIGHT = colors.HexColor('#D5F5E3')
RED         = colors.HexColor('#E74C3C')
RED_LIGHT   = colors.HexColor('#FADBD8')
BLUE        = colors.HexColor('#2980B9')
BLUE_LIGHT  = colors.HexColor('#E8F4FD')
ORANGE      = colors.HexColor('#E67E22')
ORANGE_LIGHT= colors.HexColor('#FDEBD0')
LIGHT_GREY  = colors.HexColor('#F5F7FA')
MID_GREY    = colors.HexColor('#BDC3C7')
DARK_GREY   = colors.HexColor('#566573')
WHITE       = colors.white
BLACK       = colors.HexColor('#2C3E50')

# ── Page Settings ───────────────────────────────────────────
PAGE_WIDTH, PAGE_HEIGHT = A4
LEFT_MARGIN   = 18 * mm
RIGHT_MARGIN  = 18 * mm
TOP_MARGIN    = 18 * mm
BOTTOM_MARGIN = 18 * mm
CONTENT_WIDTH = PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN

MOS_EXPLAIN = {
    'STRONG BUY ZONE': (
        GREEN,
        'Trading WELL BELOW our calculated fair value. '
        'Large safety cushion — you are paying significantly '
        'less than what the business appears to be worth.'
    ),
    'BUY ZONE': (
        BLUE,
        'Trading BELOW our calculated fair value. '
        'Reasonable safety margin. The price appears attractive '
        'relative to the underlying business fundamentals.'
    ),
    'FAIRLY VALUED': (
        ORANGE,
        'Trading NEAR our calculated fair value. Not expensive, '
        'but the margin of safety is thin. Consider waiting '
        'for a better entry price.'
    ),
    'ABOVE IV': (
        RED,
        'Trading ABOVE our calculated fair value. Based on '
        'current fundamentals, the market may be overpricing '
        'this stock. Exercise caution.'
    ),
}

PORTFOLIO_EXPLAIN = {
    'pure_dividend': (
        'What is a Pure Dividend Portfolio?',
        'This portfolio targets stocks that pay the HIGHEST CURRENT INCOME — '
        'like collecting rent on your investments every quarter. '
        'The goal is maximum cash flow from dividends RIGHT NOW, '
        'with a strict focus on payout safety and earnings stability. '
        'Ideal for investors who need reliable income today.'
    ),
    'dividend_growth': (
        'What is a Dividend Growth Portfolio?',
        'This portfolio targets stocks that GROW their dividends year after year — '
        'faster than inflation. You start with a moderate yield, but the '
        'income compounds over time. A stock paying 4% today at 10% CAGR '
        'pays 6.4% on your original cost in 5 years. '
        'Ideal for investors building long-term wealth and rising income.'
    ),
    'value': (
        'What is a Value Portfolio?',
        'This portfolio looks for stocks that are UNDERPRICED — '
        'great businesses available at a discount to their true worth. '
        'Inspired by Warren Buffett and Benjamin Graham. '
        'The goal is capital growth as the market eventually '
        'recognises the business\'s true value.'
    ),
}


def build_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='ReportTitle',
        fontSize=26, textColor=WHITE, alignment=TA_CENTER,
        fontName='Helvetica-Bold', spaceAfter=2, leading=30
    ))
    styles.add(ParagraphStyle(
        name='ReportSubtitle',
        fontSize=11, textColor=DARK_GREY, alignment=TA_CENTER,
        fontName='Helvetica', spaceAfter=2
    ))
    styles.add(ParagraphStyle(
        name='SectionHeader',
        fontSize=13, textColor=NAVY, alignment=TA_LEFT,
        fontName='Helvetica-Bold', spaceBefore=10, spaceAfter=4
    ))
    styles.add(ParagraphStyle(
        name='BodyText2',
        fontSize=9, textColor=BLACK, alignment=TA_LEFT,
        fontName='Helvetica', spaceAfter=4, leading=14
    ))
    styles.add(ParagraphStyle(
        name='SmallMuted',
        fontSize=8, textColor=DARK_GREY, alignment=TA_CENTER,
        fontName='Helvetica', spaceAfter=2
    ))
    styles.add(ParagraphStyle(
        name='Disclaimer',
        fontSize=7.5, textColor=DARK_GREY, alignment=TA_CENTER,
        fontName='Helvetica-Oblique', spaceAfter=2, leading=11
    ))
    styles.add(ParagraphStyle(
        name='GoldLabel',
        fontSize=9, textColor=NAVY, alignment=TA_LEFT,
        fontName='Helvetica-Bold', spaceAfter=3, spaceBefore=4
    ))
    styles.add(ParagraphStyle(
        name='ExplainText',
        fontSize=8.5, textColor=DARK_GREY, alignment=TA_LEFT,
        fontName='Helvetica-Oblique', spaceAfter=2, leading=13
    ))
    return styles


def score_color(score):
    if score >= 75:   return GREEN
    elif score >= 55: return BLUE
    elif score >= 40: return ORANGE
    else:             return RED


def score_bg(score):
    if score >= 75:   return GREEN_LIGHT
    elif score >= 55: return BLUE_LIGHT
    elif score >= 40: return ORANGE_LIGHT
    else:             return RED_LIGHT


def grade(score):
    if score >= 80: return 'A'
    if score >= 65: return 'B'
    if score >= 50: return 'C'
    return 'D'


def grade_label(score):
    if score >= 80: return 'STRONG'
    if score >= 65: return 'GOOD'
    if score >= 50: return 'FAIR'
    return 'WEAK'


def mos_signal(mos_pct):
    if mos_pct is None:  return 'N/A'
    if mos_pct >= 30:    return 'STRONG BUY ZONE'
    elif mos_pct >= 15:  return 'BUY ZONE'
    elif mos_pct >= 0:   return 'FAIRLY VALUED'
    else:                return 'ABOVE IV'
