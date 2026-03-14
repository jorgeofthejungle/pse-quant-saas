# ============================================================
# pdf_styles.py — Color Palette, Page Settings, Style Helpers
# PSE Quant SaaS — reports sub-module
# ============================================================

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import Flowable

# ── Stockpilot Brand Colours ─────────────────────────────────
# Matched to the Stockpilot Philippines logo:
#   Deep navy (#0D1F3C) — primary headers and backgrounds
#   Amber gold (#F0A500) — accent bars, dividers, highlights
NAVY        = colors.HexColor('#0D1F3C')   # Deep navy (logo background)
NAVY_LIGHT  = colors.HexColor('#1A3564')   # Secondary headers
GOLD        = colors.HexColor('#F0A500')   # Amber gold (logo accent)
GOLD_LIGHT  = colors.HexColor('#FDF3DC')   # Light gold tint for row backgrounds
GREEN       = colors.HexColor('#27AE60')   # Positive / buy zone
GREEN_LIGHT = colors.HexColor('#D5F5E3')
RED         = colors.HexColor('#E74C3C')   # Negative / above IV
RED_LIGHT   = colors.HexColor('#FADBD8')
BLUE        = colors.HexColor('#2471A3')   # Fairly valued
BLUE_LIGHT  = colors.HexColor('#EBF5FB')
ORANGE      = colors.HexColor('#E67E22')   # Caution
ORANGE_LIGHT= colors.HexColor('#FDEBD0')
LIGHT_GREY  = colors.HexColor('#F5F7FA')
MID_GREY    = colors.HexColor('#BDC3C7')
DARK_GREY   = colors.HexColor('#566573')
WHITE       = colors.white
BLACK       = colors.HexColor('#1A252F')

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
        'This stock is trading WELL BELOW our calculated fair value. '
        'You are paying significantly less than what the business appears to be worth. '
        'A wide margin of safety gives you more cushion if our estimates are off.'
    ),
    'BUY ZONE': (
        BLUE,
        'This stock is trading BELOW our calculated fair value. '
        'The price looks attractive relative to the underlying business fundamentals. '
        'A reasonable margin of safety is present.'
    ),
    'FAIRLY VALUED': (
        ORANGE,
        'This stock is trading NEAR our calculated fair value. '
        'It is not expensive, but the margin of safety is thin. '
        'Patient investors may want to wait for a lower entry price.'
    ),
    'ABOVE IV': (
        RED,
        'This stock is trading ABOVE our calculated fair value. '
        'Based on current fundamentals, the market may be overpricing this stock. '
        'Proceed with extra caution and verify the fundamentals carefully.'
    ),
}

PORTFOLIO_EXPLAIN = {
    'pure_dividend': (
        'What is a Pure Dividend Portfolio?',
        'Think of this like collecting rent. This portfolio finds stocks that pay '
        'the highest cash dividends right now. Every quarter, qualifying companies '
        'send cash directly to shareholders. The screening is strict: companies must '
        'have a proven track record of paying dividends, a safe payout ratio, and '
        'enough free cash flow to sustain those payments. Best suited for investors '
        'who want reliable income in their hands today.'
    ),
    'dividend_growth': (
        'What is a Dividend Growth Portfolio?',
        'This portfolio finds companies that consistently raise their dividend every '
        'year, even if the starting yield is modest. The power of compounding works '
        'in your favour over time. A stock paying 4% today that grows its dividend '
        'at 10% per year pays 6.4% on your original cost after just 5 years. '
        'Best suited for investors who are building long-term wealth and want their '
        'income to grow faster than inflation.'
    ),
    'value': (
        'What is a Value Portfolio?',
        'This portfolio hunts for great businesses that are selling at a price below '
        'what they are truly worth. Using deterministic, rule-based analysis, it employs '
        'multiple valuation metrics to estimate fair value and only includes stocks trading '
        'at a meaningful discount. The goal is capital growth as the market eventually '
        'recognises the true value of the business.'
    ),
    'unified': (
        'About StockPilot PH Rankings',
        'Rule-based rankings of PSE-listed stocks using a 4-factor fundamental score: '
        '<b>Financial Health</b> · <b>Business Improvement</b> · '
        '<b>Growth Acceleration</b> · <b>Consistency</b>. '
        'Stocks are ranked highest to lowest. Higher score = stronger, more durable fundamentals. '
        'Scores are deterministic — same data always produces the same result.'
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
        fontSize=9, textColor=GOLD, alignment=TA_LEFT,
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


# ── Investment Profile Tags ──────────────────────────────────
# Returns a list of (label, text_color, bg_color) tuples.
# Multiple tags may apply to the same stock.

def get_stock_profiles(stock: dict) -> list[tuple[str, object, object]]:
    """
    Classify a stock into one or more investment profile tags.

    Rules:
      REIT     — is_reit flag
      BANK     — is_bank flag
      HIGH INCOME — dividend_yield >= 4%
      VALUE    — mos_pct >= 15% (trading below intrinsic value)
      GROWTH   — revenue_cagr >= 8% AND (payout_ratio is None OR <= 60%)

    Returns: [(label, text_color, bg_color), ...]
    """
    tags = []

    if stock.get('is_reit'):
        tags.append(('REIT', WHITE, NAVY_LIGHT))
    elif stock.get('is_bank'):
        tags.append(('BANK', WHITE, NAVY_LIGHT))

    dy = stock.get('dividend_yield') or 0.0
    if dy >= 4.0:
        tags.append(('HIGH INCOME', BLACK, GOLD_LIGHT))

    mos = stock.get('mos_pct')
    if mos is not None and mos >= 15.0:
        tags.append(('VALUE', WHITE, GREEN))

    cagr = stock.get('revenue_cagr')
    pr   = stock.get('payout_ratio')
    if cagr is not None and cagr >= 8.0:
        if pr is None or pr <= 60.0:
            tags.append(('GROWTH', WHITE, BLUE))

    return tags


# ── Stockpilot Bar Chart Icon ────────────────────────────────
# Draws the 3-bar rising chart icon from the Stockpilot logo.
# Colors: deep navy background, amber gold bars, darker amber shadow.
_ICON_GOLD  = colors.HexColor('#F0A500')
_ICON_SHADE = colors.HexColor('#B07800')   # bottom shadow on bars


def draw_bar_icon(canv, x, y, size):
    """
    Draw the Stockpilot 3-bar rising chart icon onto a canvas.
    Args:
        canv  : ReportLab canvas object
        x, y  : bottom-left corner of the icon bounding box (points)
        size  : width = height of the icon (square)
    """
    canv.saveState()

    # Navy background square
    canv.setFillColor(NAVY)
    canv.roundRect(x, y, size, size, size * 0.07, fill=1, stroke=0)

    # Bar layout
    pad      = size * 0.11
    bar_w    = size * 0.20
    gap      = size * 0.065
    base_y   = y + pad
    max_h    = size - 2 * pad
    shadow_h = size * 0.13   # fixed absolute shadow height (same on all bars)

    # Bar heights (fraction of max_h): short, medium, tall
    fractions = [0.36, 0.63, 0.93]
    total_w   = 3 * bar_w + 2 * gap
    start_x   = x + (size - total_w) / 2

    for i, frac in enumerate(fractions):
        bx = start_x + i * (bar_w + gap)
        bh = max_h * frac
        sh = min(shadow_h, bh)

        # Darker amber shadow at the base
        canv.setFillColor(_ICON_SHADE)
        canv.rect(bx, base_y, bar_w, sh, fill=1, stroke=0)

        # Gold main bar above shadow
        canv.setFillColor(_ICON_GOLD)
        canv.rect(bx, base_y + sh, bar_w, bh - sh, fill=1, stroke=0)

    canv.restoreState()


class BarChartIcon(Flowable):
    """
    ReportLab Platypus Flowable that renders the Stockpilot bar chart icon.
    Use inside Table cells or directly in a story.
    """
    def __init__(self, size):
        Flowable.__init__(self)
        self.size   = size
        self.width  = size
        self.height = size

    def draw(self):
        draw_bar_icon(self.canv, 0, 0, self.size)
