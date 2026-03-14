# ============================================================
# pdf_cover_page.py — Cover Page & Disclaimer Page Builders
# PSE Quant SaaS — reports sub-module
# ============================================================

from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from reports.pdf_styles import (
    NAVY, NAVY_LIGHT, GOLD, GOLD_LIGHT, GREEN, GREEN_LIGHT, BLUE, BLUE_LIGHT,
    RED, RED_LIGHT, LIGHT_GREY, MID_GREY, DARK_GREY, WHITE, BLACK,
    CONTENT_WIDTH, PORTFOLIO_EXPLAIN, BarChartIcon,
)


def _build_brand_header(portfolio_name, portfolio_type=''):
    """Full-width dark navy header with bar-chart icon + title + sub-banner."""
    elements = []

    logo_cell = BarChartIcon(18 * mm)

    # "Stockpilot" and "PHILIPPINES" stacked vertically, matching the logo layout
    text_cell = Table(
        [
            [Paragraph('Stockpilot', ParagraphStyle(
                'BrandName', fontSize=22, textColor=WHITE,
                fontName='Helvetica-Bold', alignment=TA_LEFT, spaceAfter=0, leading=24
            ))],
            [Paragraph('PHILIPPINES', ParagraphStyle(
                'BrandCountry', fontSize=9, textColor=GOLD,
                fontName='Helvetica-Bold', alignment=TA_LEFT, spaceBefore=0, leading=11
            ))],
        ],
        colWidths=[CONTENT_WIDTH - 32*mm]
    )
    text_cell.setStyle(TableStyle([
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
    ]))

    icon_col_w = 22 * mm   # just enough for the 18mm icon + small gap
    brand_row = Table(
        [[logo_cell, text_cell]],
        colWidths=[icon_col_w, CONTENT_WIDTH - icon_col_w]
    )
    brand_row.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), NAVY),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 14),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
        ('LEFTPADDING',   (0, 0), (0, 0),   10),  # left edge padding
        ('RIGHTPADDING',  (0, 0), (0, 0),   0),   # no gap between icon and text
        ('LEFTPADDING',   (1, 0), (1, 0),   4),   # tight to the icon
    ]))
    elements.append(brand_row)

    # Gold accent line
    elements.append(HRFlowable(
        width=CONTENT_WIDTH, thickness=4,
        color=GOLD, spaceAfter=0, spaceBefore=0
    ))

    # Portfolio sub-banner
    _banner = (f'{portfolio_name} REPORT'
               if portfolio_type == 'unified'
               else f'{portfolio_name} PORTFOLIO REPORT')
    sub_tbl = Table(
        [[Paragraph(
            _banner,
            ParagraphStyle(
                'SubBanner', fontSize=11, textColor=NAVY,
                alignment=TA_CENTER, fontName='Helvetica-Bold'
            )
        )]],
        colWidths=[CONTENT_WIDTH]
    )
    sub_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), GOLD_LIGHT),
        ('TOPPADDING',    (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LINEBELOW',     (0, 0), (-1, -1), 2, GOLD),
    ]))
    elements.append(sub_tbl)
    return elements


def build_cover_page(styles, portfolio_type, portfolio_name,
                     run_date, total_stocks, eligible_stocks):
    elements = []

    elements += _build_brand_header(portfolio_name, portfolio_type)
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
        ('BACKGROUND',    (0, 0), (-1, -1), GOLD_LIGHT),
        ('TOPPADDING',    (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING',   (0, 0), (-1, -1), 12),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 12),
        ('LINEBEFORE',    (0, 0), (0, -1),  4, GOLD),
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
                Paragraph('Met health filter criteria'
                          if portfolio_type == 'unified'
                          else 'Met all portfolio criteria', styles['SmallMuted']),
                Paragraph('Data as of this date',       styles['SmallMuted']),
            ],
        ],
        colWidths=[CONTENT_WIDTH / 3] * 3
    )
    stats.setStyle(TableStyle([
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND',    (0, 0), (-1, -1), LIGHT_GREY),
        ('BACKGROUND',    (1, 0), (1, -1),  GOLD_LIGHT),
        ('BOX',           (0, 0), (-1, -1), 1,   NAVY),
        ('LINEABOVE',     (0, 0), (-1, 0),  2,   GOLD),
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
         'Each stock is given a score from 0 to 100. The higher the score, '
         'the better it meets our portfolio criteria. '
         'Grades: 80 and above = A (Strong).  65 to 79 = B (Good).  '
         '50 to 64 = C (Fair).  Below 50 = D (Weak).'),
        ('INTRINSIC VALUE',
         'This is our mathematical estimate of what a stock is actually worth, '
         'based on its earnings, dividends, and cash flow. '
         'Think of it as a calculated price tag for the business. '
         'It is a research reference point, not a price prediction or target.'),
        ('MARGIN OF SAFETY',
         'This is the gap between our intrinsic value estimate and the current '
         'market price. A 30% margin means the stock is trading 30% below our '
         'fair value estimate. A bigger margin gives you more protection if our '
         'calculations turn out to be slightly off.'),
        ('MoS BUY PRICE',
         'This is the price level where we consider the stock to offer good value. '
         'When the current price is at or below this level, the stock is inside '
         'the buy zone based on our model.'),
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
         'Every stock is evaluated using a fixed, deterministic formula. '
         'Each financial metric is converted to a sub-score between 0 and 100, '
         'then multiplied by its assigned weight. The sub-scores are added together '
         'to produce the final score. '
         'If you run the same data through the model twice, you will always get '
         'the same result.'),
        ('What is Margin of Safety?',
         'Margin of Safety is the percentage gap between what we calculate '
         'a business is worth (intrinsic value) and what the market is currently '
         'charging you to buy it. A larger margin means more room for error in '
         'our estimates and more protection against unexpected bad news. '
         'It is a key principle in disciplined investing.'),
        ('How Intrinsic Value is Calculated',
         'We use three separate valuation methods and combine the results. '
         '(1) Dividend Discount Model: projects future dividends and discounts '
         'them to today\'s value, used for income stocks. '
         '(2) EPS x Target PE: multiplies normalised earnings by a fair price-to-earnings '
         'multiple, used as a cross-check. '
         '(3) Discounted Cash Flow: projects free cash flow and discounts at the '
         'cost of equity, used for cash-generative businesses.'),
        ('Data Sources',
         'All financial data is sourced exclusively from PSE Edge '
         '(edge.pse.com.ph), the official disclosure platform of the '
         'Philippine Stock Exchange. Figures reflect the most recently '
         'available annual filings at the time this report was generated. '
         'No third-party data providers are used.'),
        ('IMPORTANT LEGAL DISCLAIMER',
         'THIS REPORT IS FOR RESEARCH AND EDUCATIONAL PURPOSES ONLY. '
         'IT DOES NOT CONSTITUTE INVESTMENT ADVICE OF ANY KIND. '
         'Scores, rankings, and Margin of Safety prices are the output of '
         'a mathematical model applied to historical financial data. '
         'They must not be treated as recommendations to buy or sell any security. '
         'Past performance of any model or ranking does not guarantee future results. '
         'Always conduct your own due diligence and consult a licensed financial '
         'adviser before making any investment decision.'),
    ]

    for title, body in blocks:
        elements.append(Paragraph(title, styles['GoldLabel']))
        elements.append(Paragraph(body,  styles['BodyText2']))
        elements.append(Spacer(1, 3 * mm))

    return elements
