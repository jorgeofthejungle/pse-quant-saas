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
from reportlab.lib.enums import TA_CENTER

from reports.pdf_styles import (
    NAVY, GOLD, GOLD_LIGHT, GREEN, GREEN_LIGHT, BLUE, BLUE_LIGHT,
    RED, RED_LIGHT, LIGHT_GREY, MID_GREY, DARK_GREY, WHITE, BLACK,
    CONTENT_WIDTH, PORTFOLIO_EXPLAIN,
)


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
        ('BACKGROUND',    (1, 0), (1, -1),  GREEN_LIGHT),
        ('BOX',           (0, 0), (-1, -1), 1,   NAVY),
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
