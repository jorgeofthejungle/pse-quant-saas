# ============================================================
# pdf_generator.py — PDF Report Generator v4
# PSE Quant SaaS — Phase 2
# Full explanations per metric with actual stock values
# ============================================================

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from datetime import datetime
import os

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


def build_cover_page(styles, portfolio_type, portfolio_name,
                     run_date, total_stocks, eligible_stocks):
    elements = []

    title_tbl = Table(
        [[Paragraph('PSE QUANT SAAS', styles['ReportTitle'])]],
        colWidths=[CONTENT_WIDTH]
    )
    title_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), NAVY),
        ('TOPPADDING',    (0, 0), (-1, -1), 16),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 16),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
    ]))
    elements.append(title_tbl)

    sub_tbl = Table(
        [[Paragraph(
            f'{portfolio_name} PORTFOLIO REPORT',
            ParagraphStyle(
                'SubBanner', fontSize=12, textColor=NAVY,
                alignment=TA_CENTER, fontName='Helvetica-Bold'
            )
        )]],
        colWidths=[CONTENT_WIDTH]
    )
    sub_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), GOLD_LIGHT),
        ('TOPPADDING',    (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LINEBELOW',     (0, 0), (-1, -1), 3, GOLD),
    ]))
    elements.append(sub_tbl)
    elements.append(Spacer(1, 8 * mm))

    p_title, p_desc = PORTFOLIO_EXPLAIN.get(
        portfolio_type,
        ('About This Report', 'Quantitative stock analysis report.')
    )
    desc_tbl = Table(
        [
            [Paragraph(p_title, ParagraphStyle(
                'DT', fontSize=10, textColor=NAVY,
                fontName='Helvetica-Bold'
            ))],
            [Paragraph(p_desc, ParagraphStyle(
                'DB', fontSize=9, textColor=BLACK,
                fontName='Helvetica', leading=14
            ))],
        ],
        colWidths=[CONTENT_WIDTH]
    )
    desc_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), BLUE_LIGHT),
        ('TOPPADDING',    (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING',   (0, 0), (-1, -1), 12),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 12),
        ('LINEBEFORE',    (0, 0), (0, -1),  4, BLUE),
        ('BOX',           (0, 0), (-1, -1), 0.5, MID_GREY),
    ]))
    elements.append(desc_tbl)
    elements.append(Spacer(1, 8 * mm))

    elements.append(Paragraph('REPORT SUMMARY', styles['SectionHeader']))
    elements.append(HRFlowable(
        width=CONTENT_WIDTH, thickness=2,
        color=GOLD, spaceAfter=6
    ))

    stats = Table(
        [
            [
                Paragraph('STOCKS SCREENED', styles['SmallMuted']),
                Paragraph('PASSED FILTERS',  styles['SmallMuted']),
                Paragraph('REPORT DATE',     styles['SmallMuted']),
            ],
            [
                Paragraph(str(total_stocks), ParagraphStyle(
                    'SN1', fontSize=26, textColor=NAVY,
                    alignment=TA_CENTER, fontName='Helvetica-Bold'
                )),
                Paragraph(str(eligible_stocks), ParagraphStyle(
                    'SN2', fontSize=26, textColor=GREEN,
                    alignment=TA_CENTER, fontName='Helvetica-Bold'
                )),
                Paragraph(run_date, ParagraphStyle(
                    'SN3', fontSize=9, textColor=NAVY,
                    alignment=TA_CENTER, fontName='Helvetica-Bold'
                )),
            ],
            [
                Paragraph('Total PSE stocks analyzed', styles['SmallMuted']),
                Paragraph('Met all portfolio criteria', styles['SmallMuted']),
                Paragraph('Data as of this date',       styles['SmallMuted']),
            ],
        ],
        colWidths=[CONTENT_WIDTH / 3] * 3
    )
    stats.setStyle(TableStyle([
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND',    (0, 0), (-1, -1), LIGHT_GREY),
        ('BACKGROUND',    (1, 0), (1, -1),  GREEN_LIGHT),   # entire middle column
        ('BOX',           (0, 0), (-1, -1), 1,   NAVY),
        # vertical column separators only — no horizontal lines between rows
        ('LINEAFTER',     (0, 0), (1, -1),  0.5, MID_GREY),
        ('TOPPADDING',    (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(stats)
    elements.append(Spacer(1, 8 * mm))

    elements.append(Paragraph(
        'HOW TO READ THIS REPORT', styles['SectionHeader']
    ))
    elements.append(HRFlowable(
        width=CONTENT_WIDTH, thickness=2,
        color=GOLD, spaceAfter=6
    ))

    how_to = [
        ('SCORE (0-100)',
         'Each stock scores 0-100. Higher = better. '
         '80+ = A (Strong)   65-79 = B (Good)   '
         '50-64 = C (Fair)   Below 50 = D (Weak)'),
        ('INTRINSIC VALUE',
         "Our formula's estimate of what the stock is actually WORTH "
         'based on earnings, dividends, and cash flow. '
         'Not a price prediction — a mathematical reference point.'),
        ('MARGIN OF SAFETY',
         'The gap between intrinsic value and current price. '
         '30% MoS = stock trades 30% below our fair value estimate. '
         'Bigger MoS = more cushion if our estimate is wrong.'),
        ('MoS BUY PRICE',
         'The price at which we consider the stock a good deal. '
         'If current price is AT OR BELOW this — it is in the buy zone.'),
    ]

    for title, desc in how_to:
        row = Table(
            [[
                Paragraph(title, ParagraphStyle(
                    'HT', fontSize=8.5, textColor=WHITE,
                    fontName='Helvetica-Bold', alignment=TA_CENTER
                )),
                Paragraph(desc, ParagraphStyle(
                    'HD', fontSize=8.5, textColor=BLACK,
                    fontName='Helvetica', leading=13
                )),
            ]],
            colWidths=[38*mm, CONTENT_WIDTH - 38*mm]
        )
        row.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (0, 0),   NAVY),
            ('BACKGROUND',    (1, 0), (1, 0),   LIGHT_GREY),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING',    (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LEFTPADDING',   (0, 0), (-1, -1), 8),
            ('LINEBELOW',     (0, 0), (-1, -1), 0.3, MID_GREY),
        ]))
        elements.append(row)

    elements.append(Spacer(1, 8 * mm))

    disc = Table(
        [[Paragraph(
            'FOR RESEARCH AND EDUCATIONAL PURPOSES ONLY. '
            'NOT INVESTMENT ADVICE. All scores and Margin of Safety '
            'prices are mathematical computations based on historical '
            'data. Past performance does not guarantee future results. '
            'Always conduct your own due diligence and consult a '
            'licensed financial adviser before making any investment.',
            styles['Disclaimer']
        )]],
        colWidths=[CONTENT_WIDTH]
    )
    disc.setStyle(TableStyle([
        ('BOX',           (0, 0), (-1, -1), 1,  RED),
        ('BACKGROUND',    (0, 0), (-1, -1), RED_LIGHT),
        ('TOPPADDING',    (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
    ]))
    elements.append(disc)
    elements.append(PageBreak())
    return elements


def build_rankings_table(styles, ranked_stocks, portfolio_type):
    elements = []
    elements.append(Paragraph('RANKINGS', styles['SectionHeader']))
    elements.append(HRFlowable(
        width=CONTENT_WIDTH, thickness=2,
        color=GOLD, spaceAfter=4
    ))
    elements.append(Paragraph(
        'Stocks ranked from highest to lowest score. '
        'Green MoS% = trading below intrinsic value.',
        styles['ExplainText']
    ))
    elements.append(Spacer(1, 3 * mm))

    th = ParagraphStyle(
        'TH', fontSize=8, textColor=WHITE,
        fontName='Helvetica-Bold', alignment=TA_CENTER
    )
    td = ParagraphStyle(
        'TD', fontSize=8, textColor=BLACK,
        fontName='Helvetica', alignment=TA_CENTER
    )

    if portfolio_type == 'pure_dividend':
        headers = ['#', 'Ticker', 'Company', 'Score', 'Grade',
                   'Yield', 'Payout', 'MoS%', 'Buy Price', 'Signal']
        col_w   = [8*mm, 14*mm, 36*mm, 14*mm, 18*mm,
                   14*mm, 14*mm, 12*mm, 18*mm, 26*mm]
    elif portfolio_type == 'dividend_growth':
        headers = ['#', 'Ticker', 'Company', 'Score', 'Grade',
                   'Yield', 'CAGR', 'MoS%', 'Buy Price', 'Signal']
        col_w   = [8*mm, 14*mm, 36*mm, 14*mm, 18*mm,
                   14*mm, 14*mm, 12*mm, 18*mm, 26*mm]
    elif portfolio_type == 'value':
        headers = ['#', 'Ticker', 'Company', 'Score', 'Grade',
                   'P/E', 'ROE', 'MoS%', 'Buy Price', 'Signal']
        col_w   = [8*mm, 14*mm, 36*mm, 14*mm, 18*mm,
                   14*mm, 14*mm, 12*mm, 18*mm, 26*mm]
    else:
        headers = ['#', 'Ticker', 'Company', 'Score', 'Grade',
                   'Yield', 'P/E', 'MoS%', 'Buy Price', 'Signal']
        col_w   = [8*mm, 14*mm, 36*mm, 14*mm, 18*mm,
                   14*mm, 14*mm, 12*mm, 18*mm, 26*mm]

    header_row = [Paragraph(h, th) for h in headers]
    data_rows  = [header_row]

    for i, stock in enumerate(ranked_stocks):
        sc  = stock.get('score', 0)
        mp  = stock.get('mos_pct', None)
        sig = mos_signal(mp)

        if portfolio_type == 'pure_dividend':
            cols = [
                str(i+1), stock.get('ticker', ''),
                stock.get('name', ''),
                f"{sc}/100",
                f"{grade(sc)} {grade_label(sc)}",
                f"{stock.get('dividend_yield', 0):.1f}%",
                f"{stock.get('payout_ratio', 0):.1f}%",
                f"{mp:.1f}%" if mp is not None else 'N/A',
                f"P{stock.get('mos_price', 0):.2f}"
                if stock.get('mos_price') else 'N/A',
                sig,
            ]
        elif portfolio_type == 'dividend_growth':
            cols = [
                str(i+1), stock.get('ticker', ''),
                stock.get('name', ''),
                f"{sc}/100",
                f"{grade(sc)} {grade_label(sc)}",
                f"{stock.get('dividend_yield', 0):.1f}%",
                f"+{stock.get('dividend_cagr_5y', 0):.1f}%/yr",
                f"{mp:.1f}%" if mp is not None else 'N/A',
                f"P{stock.get('mos_price', 0):.2f}"
                if stock.get('mos_price') else 'N/A',
                sig,
            ]
        elif portfolio_type == 'value':
            cols = [
                str(i+1), stock.get('ticker', ''),
                stock.get('name', ''),
                f"{sc}/100",
                f"{grade(sc)} {grade_label(sc)}",
                f"{stock.get('pe', 0):.1f}x",
                f"{stock.get('roe', 0):.1f}%",
                f"{mp:.1f}%" if mp is not None else 'N/A',
                f"P{stock.get('mos_price', 0):.2f}"
                if stock.get('mos_price') else 'N/A',
                sig,
            ]
        else:
            cols = [
                str(i+1), stock.get('ticker', ''),
                stock.get('name', ''),
                f"{sc}/100",
                f"{grade(sc)} {grade_label(sc)}",
                f"{stock.get('dividend_yield', 0):.1f}%",
                f"{stock.get('pe', 0):.1f}x",
                f"{mp:.1f}%" if mp is not None else 'N/A',
                f"P{stock.get('mos_price', 0):.2f}"
                if stock.get('mos_price') else 'N/A',
                sig,
            ]

        data_rows.append([Paragraph(str(c), td) for c in cols])

    tbl = Table(data_rows, colWidths=col_w, repeatRows=1)
    tbl_style = [
        ('BACKGROUND',    (0, 0), (-1, 0),  NAVY),
        ('TEXTCOLOR',     (0, 0), (-1, 0),  WHITE),
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE',      (0, 0), (-1, -1), 8),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('GRID',          (0, 0), (-1, -1), 0.3, MID_GREY),
        ('LINEBELOW',     (0, 0), (-1, 0),  1.5, GOLD),
    ]
    for i in range(1, len(data_rows)):
        bg = LIGHT_GREY if i % 2 == 0 else WHITE
        tbl_style.append(('BACKGROUND', (0, i), (-1, i), bg))

    for i, stock in enumerate(ranked_stocks):
        sc  = stock.get('score', 0)
        mp  = stock.get('mos_pct', None)
        sig = mos_signal(mp)
        tbl_style.append(('TEXTCOLOR',  (3, i+1), (3, i+1), score_color(sc)))
        tbl_style.append(('FONTNAME',   (3, i+1), (3, i+1), 'Helvetica-Bold'))
        tbl_style.append(('BACKGROUND', (3, i+1), (3, i+1), score_bg(sc)))
        if mp is not None:
            mc = GREEN if mp >= 15 else ORANGE if mp >= 0 else RED
            tbl_style.append(('TEXTCOLOR', (7, i+1), (7, i+1), mc))
            tbl_style.append(('FONTNAME',  (7, i+1), (7, i+1), 'Helvetica-Bold'))
        sig_col, _ = MOS_EXPLAIN.get(sig, (DARK_GREY, ''))
        tbl_style.append(('TEXTCOLOR', (9, i+1), (9, i+1), sig_col))
        tbl_style.append(('FONTNAME',  (9, i+1), (9, i+1), 'Helvetica-Bold'))

    tbl.setStyle(TableStyle(tbl_style))
    elements.append(tbl)
    return elements


def generate_overall_assessment(stock, score, portfolio_type):
    """
    Builds a plain-English paragraph explaining WHY the stock received
    its score, using the actual fundamental numbers as evidence.
    """
    ticker    = stock.get('ticker', 'This stock')
    grade_str = grade_label(score)

    strengths = []
    concerns  = []

    dy   = stock.get('dividend_yield',    0) or 0
    pr   = stock.get('payout_ratio',      0) or 0
    fcf  = stock.get('fcf_coverage',      0) or 0
    roe  = stock.get('roe',               0) or 0
    pe   = stock.get('pe',                0) or 0
    pb   = stock.get('pb',                0) or 0
    de   = stock.get('de_ratio',          0) or 0
    rev  = stock.get('revenue_cagr',      0) or 0
    cagr = stock.get('dividend_cagr_5y',  0) or 0
    ni3  = stock.get('net_income_3y',     [])

    positive_years = sum(1 for n in ni3 if n > 0)

    if portfolio_type in ('pure_dividend', 'dividend_growth'):
        if dy >= 7:
            strengths.append(
                f"a high dividend yield of {dy:.1f}% — for every PHP 100 invested "
                f"you earn PHP {dy:.2f}/year in cash"
            )
        elif dy >= 5:
            strengths.append(
                f"a solid dividend yield of {dy:.1f}%, above the PSE average"
            )
        elif dy >= 3:
            concerns.append(
                f"a modest yield of only {dy:.1f}% — below the typical income "
                f"investor target of 5%"
            )
        else:
            concerns.append(
                f"a low yield of {dy:.1f}%, making it a weak income candidate"
            )

        if pr and 30 <= pr <= 70:
            strengths.append(
                f"a healthy payout ratio of {pr:.1f}%, meaning the company pays "
                f"shareholders well while retaining enough profit to reinvest"
            )
        elif pr and pr > 85:
            concerns.append(
                f"a high payout ratio of {pr:.1f}%, which is stretched — any "
                f"earnings decline could force a dividend cut"
            )

        if fcf >= 1.5:
            strengths.append(
                f"strong FCF coverage of {fcf:.1f}x, confirming the dividend "
                f"is funded by real cash, not just accounting profit"
            )
        elif 0 < fcf < 1.0:
            concerns.append(
                f"FCF coverage of only {fcf:.1f}x — the company does not generate "
                f"enough free cash to fully cover what it pays in dividends"
            )

        if cagr >= 5:
            strengths.append(
                f"dividend growth of {cagr:.1f}%/year over 5 years, meaning "
                f"shareholders are getting a rising income stream"
            )
        elif cagr < 0:
            concerns.append(
                f"a shrinking dividend (CAGR {cagr:.1f}%/yr over 5 years)"
            )

    if portfolio_type == 'value':
        if pe and pe <= 10:
            strengths.append(
                f"a low P/E of {pe:.1f}x — you pay only PHP {pe:.1f} for every "
                f"PHP 1 of annual earnings, which is cheap by PSE standards"
            )
        elif pe and pe >= 25:
            concerns.append(
                f"an expensive P/E of {pe:.1f}x — the market is pricing in "
                f"significant growth that may not materialise"
            )

        if pb and pb <= 1.0:
            strengths.append(
                f"a P/B of {pb:.2f}x, meaning you buy the company's assets "
                f"at a discount to book value"
            )
        elif pb and pb > 2.5:
            concerns.append(
                f"a premium P/B of {pb:.2f}x — you are paying significantly "
                f"above the company's net asset value"
            )

        if rev >= 10:
            strengths.append(
                f"revenue growing at {rev:.1f}%/year, well ahead of inflation"
            )
        elif rev < 0:
            concerns.append(
                f"declining revenue (CAGR {rev:.1f}%/yr) — a shrinking "
                f"top line threatens future earnings"
            )

    # ROE and debt apply to all portfolios
    if roe >= 15:
        strengths.append(
            f"ROE of {roe:.1f}%, showing management deploys capital efficiently "
            f"(Buffett's benchmark is 15%+)"
        )
    elif roe < 8:
        concerns.append(
            f"below-average ROE of {roe:.1f}%, suggesting the business earns "
            f"poor returns on shareholder money"
        )

    if de <= 0.5:
        strengths.append(
            f"a low debt/equity of {de:.2f}x — the company is largely "
            f"self-funded and resilient to rate increases"
        )
    elif de > 2.0:
        concerns.append(
            f"high leverage at {de:.2f}x debt/equity, which amplifies "
            f"risk in an economic downturn"
        )

    if positive_years == 3:
        strengths.append("profitability in all 3 of the last 3 years")
    elif positive_years < 3:
        concerns.append(
            f"only {positive_years} profitable year(s) out of the last 3 — "
            f"inconsistent earnings are a red flag"
        )

    # Assemble the text
    _display = {
        'pure_dividend':   'Pure Dividend',
        'dividend_growth': 'Dividend Growth',
        'value':           'Value',
    }
    lines = [f"{ticker} earns a {grade_str} score of {score}/100 for the "
             f"{_display.get(portfolio_type, portfolio_type)} portfolio."]

    if strengths:
        s_text = "; ".join(strengths)
        lines.append(f"Key positives: {s_text}.")

    if concerns:
        c_text = "; ".join(concerns)
        lines.append(f"Areas of concern: {c_text}.")

    iv = stock.get('intrinsic_value')
    cp = stock.get('current_price')
    mp = stock.get('mos_pct')
    if iv and cp and mp is not None:
        if mp >= 15:
            lines.append(
                f"At PHP {cp:.2f}, the stock trades {mp:.1f}% below our calculated "
                f"intrinsic value of PHP {iv:.2f} — offering a meaningful margin of safety."
            )
        elif mp >= 0:
            lines.append(
                f"At PHP {cp:.2f}, the stock trades close to our intrinsic value "
                f"estimate of PHP {iv:.2f} — fairly priced but not deeply discounted."
            )
        else:
            lines.append(
                f"At PHP {cp:.2f}, the stock trades {abs(mp):.1f}% ABOVE our intrinsic "
                f"value estimate of PHP {iv:.2f} — consider waiting for a better entry."
            )

    return "  ".join(lines)


def build_stock_detail(styles, stock, rank, portfolio_type):
    elements = []
    sc        = stock.get('score', 0)
    mos_pct   = stock.get('mos_pct', None)
    mos_price = stock.get('mos_price', None)
    iv        = stock.get('intrinsic_value', None)
    sig       = mos_signal(mos_pct)
    sig_col, sig_desc = MOS_EXPLAIN.get(sig, (DARK_GREY, ''))

    # ── Stock header ──
    hdr = Table(
        [[
            Paragraph(
                f"#{rank}  {stock.get('ticker', '')}",
                ParagraphStyle(
                    'Tk', fontSize=13, textColor=GOLD,
                    fontName='Helvetica-Bold'
                )
            ),
            Paragraph(
                stock.get('name', ''),
                ParagraphStyle(
                    'SN', fontSize=10, textColor=WHITE,
                    fontName='Helvetica'
                )
            ),
            Paragraph(
                f"{sc}/100",
                ParagraphStyle(
                    'ScH', fontSize=15, textColor=GOLD,
                    fontName='Helvetica-Bold', alignment=TA_RIGHT
                )
            ),
        ]],
        colWidths=[28*mm, CONTENT_WIDTH - 72*mm, 44*mm]
    )
    hdr.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), NAVY),
        ('TOPPADDING',    (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING',   (0, 0), (0,  0),  10),
        ('RIGHTPADDING',  (-1,0), (-1, 0),  10),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEBELOW',     (0, 0), (-1, -1), 2, GOLD),
    ]))
    elements.append(KeepTogether([hdr]))
    elements.append(Spacer(1, 3 * mm))

    # ── Grade badge ──
    grade_tbl = Table(
        [
            [Paragraph('GRADE', ParagraphStyle(
                'GL', fontSize=7, textColor=DARK_GREY,
                fontName='Helvetica', alignment=TA_CENTER
            ))],
            [Paragraph(
                f"{grade(sc)} — {grade_label(sc)}",
                ParagraphStyle(
                    'GV', fontSize=11, textColor=score_color(sc),
                    fontName='Helvetica-Bold', alignment=TA_CENTER
                )
            )],
        ],
        colWidths=[CONTENT_WIDTH / 2 - 2*mm]
    )
    grade_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), score_bg(sc)),
        ('BOX',           (0, 0), (-1, -1), 1, score_color(sc)),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
    ]))

    # ── Signal badge ──
    signal_tbl = Table(
        [
            [Paragraph('SIGNAL', ParagraphStyle(
                'SL', fontSize=7, textColor=DARK_GREY,
                fontName='Helvetica', alignment=TA_CENTER
            ))],
            [Paragraph(
                sig,
                ParagraphStyle(
                    'SV', fontSize=11, textColor=sig_col,
                    fontName='Helvetica-Bold', alignment=TA_CENTER
                )
            )],
        ],
        colWidths=[CONTENT_WIDTH / 2 - 2*mm]
    )
    signal_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), LIGHT_GREY),
        ('BOX',           (0, 0), (-1, -1), 1, sig_col),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
    ]))

    # ── Badges side by side ──
    badges = Table(
        [[grade_tbl, signal_tbl]],
        colWidths=[CONTENT_WIDTH / 2, CONTENT_WIDTH / 2]
    )
    badges.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(badges)

    # ── Signal explanation ──
    if sig_desc:
        elements.append(Spacer(1, 2 * mm))
        exp_tbl = Table(
            [[Paragraph(sig_desc, ParagraphStyle(
                'SE', fontSize=8.5, textColor=sig_col,
                fontName='Helvetica-Oblique', leading=13
            ))]],
            colWidths=[CONTENT_WIDTH]
        )
        exp_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), LIGHT_GREY),
            ('LEFTPADDING',   (0, 0), (-1, -1), 10),
            ('TOPPADDING',    (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LINEBEFORE',    (0, 0), (0, -1),  3, sig_col),
        ]))
        elements.append(exp_tbl)

    elements.append(Spacer(1, 3 * mm))

    # ── Overall Assessment ──
    assessment_text = generate_overall_assessment(stock, sc, portfolio_type)
    elements.append(Paragraph('OVERALL ASSESSMENT', styles['GoldLabel']))
    assess_tbl = Table(
        [[Paragraph(assessment_text, ParagraphStyle(
            'Assess', fontSize=8.5, textColor=BLACK,
            fontName='Helvetica', leading=13
        ))]],
        colWidths=[CONTENT_WIDTH]
    )
    assess_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), BLUE_LIGHT),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
        ('TOPPADDING',    (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LINEBEFORE',    (0, 0), (0, -1),  3, NAVY),
        ('BOX',           (0, 0), (-1, -1), 0.5, MID_GREY),
    ]))
    elements.append(assess_tbl)
    elements.append(Spacer(1, 3 * mm))

    # ── Key numbers ──
    elements.append(Paragraph('KEY NUMBERS', styles['GoldLabel']))

    price_data = [
        ['CURRENT PRICE',
         f"P{stock.get('current_price', 0):.2f}",
         'What you pay today on the stock exchange'],
        ['INTRINSIC VALUE',
         f"P{iv:.2f}" if iv else 'N/A',
         "Our formula's estimate of what this stock is worth"],
        ['MoS BUY PRICE',
         f"P{mos_price:.2f}" if mos_price else 'N/A',
         'Price at which we consider this stock a good deal'],
        ['MARGIN OF SAFETY',
         f"{mos_pct:.1f}%" if mos_pct is not None else 'N/A',
         'How far below intrinsic value the stock trades (higher = safer)'],
    ]

    if portfolio_type in ('pure_dividend', 'dividend_growth'):
        price_data += [
            ['DIVIDEND YIELD',
             f"{stock.get('dividend_yield', 0):.2f}%",
             'Annual cash income per P100 invested'],
            ['PAYOUT RATIO',
             f"{stock.get('payout_ratio', 0):.1f}%",
             '% of profits paid as dividends (30-70% is healthy)'],
        ]
    if portfolio_type == 'value':
        price_data += [
            ['P/E RATIO',
             f"{stock.get('pe', 0):.1f}x",
             'Price per P1 of annual profit (lower = cheaper)'],
            ['ROE',
             f"{stock.get('roe', 0):.1f}%",
             'How efficiently management uses your money'],
            ['DEBT / EQUITY',
             f"{stock.get('de_ratio', 0):.2f}x",
             'How much debt vs assets (lower = safer)'],
        ]

    price_rows = []
    for label, value, explain in price_data:
        price_rows.append([
            Paragraph(label, ParagraphStyle(
                'PL', fontSize=8, textColor=NAVY,
                fontName='Helvetica-Bold'
            )),
            Paragraph(value, ParagraphStyle(
                'PV', fontSize=9, textColor=NAVY,
                fontName='Helvetica-Bold'
            )),
            Paragraph(explain, ParagraphStyle(
                'PE', fontSize=7.5, textColor=DARK_GREY,
                fontName='Helvetica-Oblique', leading=11
            )),
        ])

    price_tbl = Table(
        price_rows,
        colWidths=[42*mm, 28*mm, CONTENT_WIDTH - 70*mm]
    )
    price_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (0, -1),  LIGHT_GREY),
        ('GRID',          (0, 0), (-1, -1), 0.3, MID_GREY),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEAFTER',     (0, 0), (0, -1),  1,   GOLD),
        ('LINEAFTER',     (1, 0), (1, -1),  0.5, MID_GREY),
    ]))
    elements.append(price_tbl)
    elements.append(Spacer(1, 3 * mm))

    # ── Score breakdown with stock-specific explanations ──
    breakdown = stock.get('score_breakdown', {})
    if breakdown:
        elements.append(Paragraph('SCORE BREAKDOWN', styles['GoldLabel']))
        elements.append(Paragraph(
            'Each factor below contributed points to the final score. '
            'Full bar = perfect 100/100 on that factor. '
            'The explanation below each bar tells you exactly '
            'why this stock scored what it scored.',
            styles['ExplainText']
        ))
        elements.append(Spacer(1, 2 * mm))

        for metric, data in breakdown.items():
            sub         = data.get('score', 0)
            wt          = data.get('weight', 0)
            contrib     = round(sub * wt, 1)
            filled      = int(sub / 10)
            empty       = 10 - filled
            bar_col     = score_color(sub)
            explanation = data.get('explanation', '')

            # Use metric name from explanation key or clean it up
            metric_name = metric.replace('_', ' ').upper()

            bar_row = Table(
                [[
                    Paragraph(metric_name, ParagraphStyle(
                        'MN', fontSize=8, textColor=NAVY,
                        fontName='Helvetica-Bold'
                    )),
                    Paragraph(
                        '█' * filled + '░' * empty,
                        ParagraphStyle(
                            'Bar', fontSize=9, textColor=bar_col,
                            fontName='Courier'
                        )
                    ),
                    Paragraph(
                        f"{sub:.0f}/100  x{wt:.0%}  =  {contrib:.1f}pts",
                        ParagraphStyle(
                            'Pts', fontSize=8, textColor=NAVY,
                            fontName='Helvetica-Bold',
                            alignment=TA_RIGHT
                        )
                    ),
                ]],
                colWidths=[48*mm, 55*mm, CONTENT_WIDTH - 103*mm]
            )
            bar_row.setStyle(TableStyle([
                ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING',    (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('BACKGROUND',    (0, 0), (-1, -1), LIGHT_GREY),
            ]))
            elements.append(bar_row)

            # Stock-specific explanation underneath each bar
            if explanation:
                exp_row = Table(
                    [[Paragraph(
                        explanation,
                        ParagraphStyle(
                            'Exp', fontSize=7.5, textColor=DARK_GREY,
                            fontName='Helvetica-Oblique', leading=11
                        )
                    )]],
                    colWidths=[CONTENT_WIDTH]
                )
                exp_row.setStyle(TableStyle([
                    ('BACKGROUND',    (0, 0), (-1, -1), WHITE),
                    ('LEFTPADDING',   (0, 0), (-1, -1), 10),
                    ('TOPPADDING',    (0, 0), (-1, -1), 3),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ('LINEBEFORE',    (0, 0), (0, -1),  2, bar_col),
                    ('LINEBELOW',     (0, 0), (-1, -1), 0.3, MID_GREY),
                ]))
                elements.append(exp_row)

            elements.append(Spacer(1, 1 * mm))

    # ── Sentiment panel (injected after score breakdown) ──
    elements += build_sentiment_panel(stock)

    return elements


SENTIMENT_COLORS = {
    'Positive': GREEN,
    'Neutral':  ORANGE,
    'Negative': RED,
}
SENTIMENT_BGS = {
    'Positive': GREEN_LIGHT,
    'Neutral':  ORANGE_LIGHT,
    'Negative': RED_LIGHT,
}


def build_sentiment_panel(stock) -> list:
    """
    Builds a sentiment panel for one stock's detail page.
    Returns a list of flowable elements (may be empty if no data).
    """
    sd = stock.get('sentiment_data')
    elements = []

    elements.append(Spacer(1, 3 * mm))
    elements.append(Paragraph('NEWS SENTIMENT', ParagraphStyle(
        'SentHdr', fontSize=9, textColor=NAVY,
        fontName='Helvetica-Bold', spaceAfter=3
    )))

    if not sd:
        note_tbl = Table(
            [[Paragraph(
                'No recent news headlines found for this stock.',
                ParagraphStyle('NoNews', fontSize=8, textColor=DARK_GREY,
                               fontName='Helvetica-Oblique')
            )]],
            colWidths=[CONTENT_WIDTH]
        )
        note_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), LIGHT_GREY),
            ('LEFTPADDING',   (0, 0), (-1, -1), 10),
            ('TOPPADDING',    (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('BOX',           (0, 0), (-1, -1), 0.5, MID_GREY),
        ]))
        elements.append(note_tbl)
        return elements

    category = sd.get('category', 'Neutral')
    score    = sd.get('score', 0.0)
    summary  = sd.get('summary', '')
    events   = sd.get('key_events') or []
    opp_flag = sd.get('opportunistic_flag', 0)
    risk_flag = sd.get('risk_flag', 0)
    col      = SENTIMENT_COLORS.get(category, DARK_GREY)
    bg_col   = SENTIMENT_BGS.get(category, LIGHT_GREY)

    # Category badge + score bar
    bar_filled = min(10, max(0, int((score + 1) / 2 * 10)))  # map -1..1 to 0..10
    bar_empty  = 10 - bar_filled

    badge_row = Table(
        [[
            Paragraph(category.upper(), ParagraphStyle(
                'SentCat', fontSize=9, textColor=WHITE,
                fontName='Helvetica-Bold', alignment=TA_CENTER
            )),
            Paragraph(
                '█' * bar_filled + '░' * bar_empty,
                ParagraphStyle('SentBar', fontSize=9, textColor=col,
                               fontName='Courier')
            ),
            Paragraph(
                f"Score: {score:+.2f}",
                ParagraphStyle('SentScore', fontSize=8, textColor=col,
                               fontName='Helvetica-Bold', alignment=TA_RIGHT)
            ),
        ]],
        colWidths=[28*mm, 60*mm, CONTENT_WIDTH - 88*mm]
    )
    badge_row.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (0, 0),   col),
        ('BACKGROUND',    (1, 0), (-1, 0),  bg_col),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        ('BOX',           (0, 0), (-1, -1), 0.5, col),
    ]))
    elements.append(badge_row)

    # Summary
    if summary:
        sum_tbl = Table(
            [[Paragraph(summary, ParagraphStyle(
                'SentSum', fontSize=8, textColor=BLACK,
                fontName='Helvetica', leading=12
            ))]],
            colWidths=[CONTENT_WIDTH]
        )
        sum_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), LIGHT_GREY),
            ('LEFTPADDING',   (0, 0), (-1, -1), 10),
            ('TOPPADDING',    (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LINEBEFORE',    (0, 0), (0, -1),  2, col),
        ]))
        elements.append(sum_tbl)

    # Key events
    if events:
        events_text = '  |  '.join(events)
        ev_tbl = Table(
            [[Paragraph(
                f"Key events: {events_text}",
                ParagraphStyle('SentEv', fontSize=7.5, textColor=DARK_GREY,
                               fontName='Helvetica-Oblique', leading=11)
            )]],
            colWidths=[CONTENT_WIDTH]
        )
        ev_tbl.setStyle(TableStyle([
            ('LEFTPADDING',   (0, 0), (-1, -1), 10),
            ('TOPPADDING',    (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(ev_tbl)

    # Flags
    flags = []
    if opp_flag:
        flags.append(('OPPORTUNISTIC WATCH', GREEN))
    if risk_flag:
        flags.append(('RISK FLAG', RED))
    if flags:
        flag_cells = [
            Paragraph(
                f"  {label}  ",
                ParagraphStyle('FlagTxt', fontSize=7.5, textColor=WHITE,
                               fontName='Helvetica-Bold', alignment=TA_CENTER)
            )
            for label, _ in flags
        ]
        flag_cols = [30*mm] * len(flag_cells)
        flag_tbl = Table([flag_cells], colWidths=flag_cols)
        flag_style = [
            ('TOPPADDING',    (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]
        for idx, (_, fc) in enumerate(flags):
            flag_style.append(('BACKGROUND', (idx, 0), (idx, 0), fc))
        flag_tbl.setStyle(TableStyle(flag_style))
        elements.append(Spacer(1, 1 * mm))
        elements.append(flag_tbl)

    return elements


def build_news_overview_section(ranked_stocks) -> list:
    """
    Builds a one-page News Sentiment Overview section.
    Shows one summary row per stock (only those with sentiment_data).
    Includes an Opportunistic Watch sub-section.
    """
    stocks_with_news = [s for s in ranked_stocks if s.get('sentiment_data')]
    if not stocks_with_news:
        return []

    elements = []
    elements.append(PageBreak())
    elements.append(Paragraph('NEWS SENTIMENT OVERVIEW', ParagraphStyle(
        'NewsSHdr', fontSize=13, textColor=NAVY,
        fontName='Helvetica-Bold', spaceBefore=0, spaceAfter=4
    )))
    elements.append(HRFlowable(
        width=CONTENT_WIDTH, thickness=2,
        color=GOLD, spaceAfter=4
    ))
    elements.append(Paragraph(
        'Headlines sourced from Yahoo Finance, BusinessWorld, and Inquirer Business. '
        'Sentiment is classified by AI (Claude Haiku) for informational purposes only. '
        'It does not affect numerical scores.',
        ParagraphStyle('NewsSNote', fontSize=8, textColor=DARK_GREY,
                       fontName='Helvetica-Oblique', leading=12, spaceAfter=6)
    ))

    th = ParagraphStyle('NSTH', fontSize=8, textColor=WHITE,
                        fontName='Helvetica-Bold', alignment=TA_CENTER)
    td = ParagraphStyle('NSTD', fontSize=8, textColor=BLACK,
                        fontName='Helvetica', alignment=TA_LEFT)

    header = [Paragraph(h, th) for h in ['Ticker', 'Sentiment', 'Score', 'Summary']]
    col_w  = [14*mm, 22*mm, 16*mm, CONTENT_WIDTH - 52*mm]
    rows   = [header]

    for stock in ranked_stocks:
        sd = stock.get('sentiment_data')
        if not sd:
            continue
        category = sd.get('category', 'Neutral')
        score    = sd.get('score', 0.0)
        summary  = sd.get('summary', '')[:160]
        col      = SENTIMENT_COLORS.get(category, DARK_GREY)
        rows.append([
            Paragraph(stock.get('ticker', ''), ParagraphStyle(
                'NSTK', fontSize=8, textColor=NAVY,
                fontName='Helvetica-Bold'
            )),
            Paragraph(category, ParagraphStyle(
                'NSCAT', fontSize=8, textColor=col,
                fontName='Helvetica-Bold'
            )),
            Paragraph(f"{score:+.2f}", ParagraphStyle(
                'NSSC', fontSize=8, textColor=col,
                fontName='Helvetica-Bold', alignment=TA_CENTER
            )),
            Paragraph(summary, td),
        ])

    tbl = Table(rows, colWidths=col_w, repeatRows=1)
    tbl_style = [
        ('BACKGROUND',    (0, 0), (-1, 0),  NAVY),
        ('ALIGN',         (0, 0), (-1, 0),  'CENTER'),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (-1, -1), 5),
        ('GRID',          (0, 0), (-1, -1), 0.3, MID_GREY),
        ('LINEBELOW',     (0, 0), (-1, 0),  1.5, GOLD),
    ]
    for i in range(1, len(rows)):
        bg = LIGHT_GREY if i % 2 == 0 else WHITE
        tbl_style.append(('BACKGROUND', (0, i), (-1, i), bg))
    tbl.setStyle(TableStyle(tbl_style))
    elements.append(tbl)

    # Opportunistic Watch sub-section
    opp_stocks = [
        s for s in ranked_stocks
        if s.get('sentiment_data', {}).get('opportunistic_flag')
    ]
    if opp_stocks:
        elements.append(Spacer(1, 6 * mm))
        elements.append(Paragraph('OPPORTUNISTIC WATCH', ParagraphStyle(
            'OppHdr', fontSize=11, textColor=GREEN,
            fontName='Helvetica-Bold', spaceAfter=4
        )))
        elements.append(Paragraph(
            'The following stocks have positive near-term news catalysts '
            'that may be worth monitoring alongside their fundamental scores. '
            'This is not a buy recommendation.',
            ParagraphStyle('OppNote', fontSize=8, textColor=DARK_GREY,
                           fontName='Helvetica-Oblique', leading=12, spaceAfter=4)
        ))
        for stock in opp_stocks:
            sd      = stock.get('sentiment_data', {})
            summary = sd.get('summary', '')
            events  = '  |  '.join(sd.get('key_events') or [])
            opp_tbl = Table(
                [[
                    Paragraph(stock.get('ticker', ''), ParagraphStyle(
                        'OppTk', fontSize=9, textColor=WHITE,
                        fontName='Helvetica-Bold', alignment=TA_CENTER
                    )),
                    Paragraph(
                        f"{summary}  {('['+events+']') if events else ''}",
                        ParagraphStyle('OppTxt', fontSize=8.5, textColor=BLACK,
                                       fontName='Helvetica', leading=13)
                    ),
                ]],
                colWidths=[16*mm, CONTENT_WIDTH - 16*mm]
            )
            opp_tbl.setStyle(TableStyle([
                ('BACKGROUND',    (0, 0), (0, 0),   GREEN),
                ('BACKGROUND',    (1, 0), (1, 0),   GREEN_LIGHT),
                ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING',    (0, 0), (-1, -1), 7),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
                ('LEFTPADDING',   (0, 0), (-1, -1), 7),
                ('LINEBELOW',     (0, 0), (-1, -1), 0.3, MID_GREY),
            ]))
            elements.append(opp_tbl)

    return elements


def build_disclaimer_page(styles):
    elements = []
    elements.append(PageBreak())
    elements.append(Paragraph(
        'METHODOLOGY & DISCLAIMER', styles['SectionHeader']
    ))
    elements.append(HRFlowable(
        width=CONTENT_WIDTH, thickness=2,
        color=GOLD, spaceAfter=8
    ))

    blocks = [
        ('How Scores Are Calculated',
         'All scores use a deterministic (fixed formula) multi-factor '
         'model. Each metric is normalized to a 0-100 sub-score and '
         'multiplied by its weight. The same financial data will always '
         'produce the same score — no AI guesswork is involved.'),
        ('What is Margin of Safety?',
         'Margin of Safety (MoS) is a concept from value investing. '
         'It is the gap between what we calculate a stock is worth '
         '(intrinsic value) and what it currently costs to buy. '
         'A larger MoS means more room for error in our estimates.'),
        ('How Intrinsic Value is Calculated',
         'We use three methods: (1) Dividend Discount Model for income '
         'stocks, (2) Normalised EPS x Target PE for earnings-based '
         'valuation, and (3) Discounted Cash Flow for cash-generative '
         'businesses. The hybrid portfolio blends all three.'),
        ('Data Sources',
         'Financial data is sourced from PSE Edge (edge.pse.com.ph). '
         'All figures reflect the most recently available annual '
         'disclosures at the time this report was generated.'),
        ('IMPORTANT LEGAL DISCLAIMER',
         'THIS REPORT IS FOR RESEARCH AND EDUCATIONAL PURPOSES ONLY. '
         'IT DOES NOT CONSTITUTE INVESTMENT ADVICE. Scores, rankings, '
         'and Margin of Safety prices are mathematical computations '
         'and must not be treated as recommendations to buy or sell '
         'any security. Past performance does not guarantee future '
         'results. Always conduct your own due diligence and consult '
         'a licensed financial adviser before making any investment '
         'decision.'),
    ]

    for title, body in blocks:
        elements.append(Paragraph(title, styles['GoldLabel']))
        elements.append(Paragraph(body,  styles['BodyText2']))
        elements.append(Spacer(1, 3 * mm))

    return elements


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
    elements += build_rankings_table(
        styles, ranked_stocks, portfolio_type
    )
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
        elements += build_stock_detail(
            styles, stock, i + 1, portfolio_type
        )

    elements += build_disclaimer_page(styles)

    doc.build(elements)
    print(f"Report saved: {output_path}")
    return output_path