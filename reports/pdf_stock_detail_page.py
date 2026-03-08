# ============================================================
# pdf_stock_detail_page.py — Per-Stock Detail Page Builder
# PSE Quant SaaS — reports sub-module
# ============================================================

from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle, KeepTogether
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER

from reports.pdf_styles import (
    NAVY, GOLD, BLUE_LIGHT, LIGHT_GREY, MID_GREY, DARK_GREY, WHITE, BLACK,
    CONTENT_WIDTH, MOS_EXPLAIN,
    score_color, score_bg, grade, grade_label, mos_signal,
)
from reports.pdf_rankings_table import generate_overall_assessment
from reports.pdf_sentiment import build_sentiment_panel
from reports.pdf_momentum import build_momentum_panel


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
                f"{grade(sc)}  {grade_label(sc)}",
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
            'Full bar = top contributing factor; each bar shows points earned '
            'relative to the highest contributor. '
            'The explanation below each bar tells you exactly '
            'why this stock scored what it scored.',
            styles['ExplainText']
        ))
        elements.append(Spacer(1, 2 * mm))

        max_contrib = max(
            (d.get('score', 0) * d.get('weight', 0) for d in breakdown.values()),
            default=1.0
        ) or 1.0

        for metric, data in breakdown.items():
            sub         = data.get('score', 0)
            wt          = data.get('weight', 0)
            contrib     = round(sub * wt, 1)
            bar_fill    = (sub * wt) / max_contrib
            filled      = round(bar_fill * 10)
            empty       = 10 - filled
            bar_col     = score_color(sub)
            explanation = data.get('explanation', '')

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

    # ── Momentum analysis panel (after score breakdown, before sentiment) ──
    elements += build_momentum_panel(stock, styles)

    # ── Sentiment panel ──
    elements += build_sentiment_panel(stock)

    return elements
