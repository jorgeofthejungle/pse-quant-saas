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
    score_color, score_bg, grade, grade_label, mos_signal, get_stock_profiles,
)
from reportlab.lib import colors as _rl_colors

# Segment health score colours
COLOUR_SEG_GOOD = _rl_colors.HexColor('#27AE60')
COLOUR_SEG_FAIR = _rl_colors.HexColor('#E67E22')
COLOUR_SEG_WEAK = _rl_colors.HexColor('#E74C3C')
from reports.pdf_rankings_table import generate_overall_assessment


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

    # ── Confidence badge ──
    confidence = stock.get('confidence', 1.0)
    if confidence >= 0.9:
        conf_label = 'High Confidence (5yr data)'
    elif confidence >= 0.8:
        conf_label = 'Medium Confidence (3-4yr data)'
    elif confidence >= 0.65:
        conf_label = 'Limited Data (2yr)'
    else:
        conf_label = 'Insufficient Data'
    elements.append(Spacer(1, 2 * mm))
    elements.append(Paragraph(
        f'Data confidence: {conf_label}',
        ParagraphStyle(
            'ConfBadge', fontSize=7.5, textColor=MID_GREY,
            fontName='Helvetica', alignment=TA_CENTER,
        )
    ))

    # ── Investment profile tags ──
    profiles = get_stock_profiles(stock)
    if profiles:
        elements.append(Spacer(1, 2 * mm))
        tag_cells = []
        for label, txt_col, bg_col in profiles:
            tag_cells.append(Paragraph(
                f'  {label}  ',
                ParagraphStyle(
                    f'Tag_{label}', fontSize=7.5, textColor=txt_col,
                    fontName='Helvetica-Bold', alignment=TA_CENTER,
                    backColor=bg_col,
                )
            ))
        # Pad to fill the row (up to 5 tags max)
        col_w = CONTENT_WIDTH / max(len(tag_cells), 1)
        tag_tbl = Table(
            [tag_cells],
            colWidths=[col_w] * len(tag_cells)
        )
        tag_tbl.setStyle(TableStyle([
            ('TOPPADDING',    (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING',   (0, 0), (-1, -1), 4),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
            ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            *[('BACKGROUND', (i, 0), (i, 0), profiles[i][2])
              for i in range(len(profiles))],
        ]))
        elements.append(tag_tbl)

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
             f"{stock.get('dividend_yield') or 0:.2f}%",
             'Annual cash income per P100 invested'],
            ['PAYOUT RATIO',
             f"{stock.get('payout_ratio') or 0:.1f}%",
             '% of profits paid as dividends (30-70% is healthy)'],
        ]
    if portfolio_type == 'value':
        price_data += [
            ['P/E RATIO',
             f"{stock.get('pe') or 0:.1f}x",
             'Price per P1 of annual profit (lower = cheaper)'],
            ['ROE',
             f"{stock.get('roe') or 0:.1f}%",
             'How efficiently management uses your money'],
            ['DEBT / EQUITY',
             f"{stock.get('de_ratio') or 0:.2f}x",
             'How much debt vs assets (lower = safer)'],
        ]
    if portfolio_type == 'unified':
        roe_val  = stock.get('roe')
        de_val   = stock.get('de_ratio')
        rev_cagr = stock.get('revenue_cagr')
        dy_val   = stock.get('dividend_yield')
        price_data += [
            ['ROE',
             f"{roe_val:.1f}%" if roe_val is not None else 'N/A',
             'Return on equity — management efficiency (>15% = strong)'],
            ['DEBT / EQUITY',
             f"{de_val:.2f}x" if de_val is not None else 'N/A',
             'How much the company relies on borrowed money (lower = safer)'],
            ['REVENUE GROWTH',
             f"{rev_cagr:.1f}%" if rev_cagr is not None else 'N/A',
             '3-5 year compound annual revenue growth rate'],
        ]
        if dy_val and dy_val > 0:
            price_data.append([
                'DIVIDEND YIELD',
                f"{dy_val:.2f}%",
                'Annual cash income per P100 invested (0% = no dividend paid)',
            ])

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

    # ── Conglomerate segment breakdown (holding firms only) ──
    cong_data = stock.get('breakdown', {}).get('conglomerate') if stock.get('breakdown') else None
    if cong_data and cong_data.get('segments'):
        elements.append(Paragraph('SEGMENT BREAKDOWN', styles['GoldLabel']))
        elements.append(Paragraph(
            cong_data.get('blend_note', ''),
            styles['ExplainText']
        ))
        elements.append(Spacer(1, 2 * mm))

        seg_header = [
            Paragraph('Segment',       ParagraphStyle('SH', fontSize=7, textColor=DARK_GREY, fontName='Helvetica-Bold')),
            Paragraph('Listed',        ParagraphStyle('SH', fontSize=7, textColor=DARK_GREY, fontName='Helvetica-Bold')),
            Paragraph('Rev %',         ParagraphStyle('SH', fontSize=7, textColor=DARK_GREY, fontName='Helvetica-Bold', alignment=TA_RIGHT)),
            Paragraph('Health Score',  ParagraphStyle('SH', fontSize=7, textColor=DARK_GREY, fontName='Helvetica-Bold', alignment=TA_RIGHT)),
        ]
        seg_rows = [seg_header]
        for seg in cong_data['segments']:
            hs  = seg.get('health_score')
            rev = seg.get('revenue_share')
            hs_col = (
                COLOUR_SEG_GOOD if hs and hs >= 70 else
                COLOUR_SEG_FAIR if hs and hs >= 45 else
                COLOUR_SEG_WEAK if hs else DARK_GREY
            )
            seg_rows.append([
                Paragraph(seg.get('segment_name', ''), ParagraphStyle('SN', fontSize=8, textColor=BLACK, fontName='Helvetica')),
                Paragraph(seg.get('segment_ticker') or '—', ParagraphStyle('ST', fontSize=8, textColor=DARK_GREY, fontName='Helvetica')),
                Paragraph(f"{rev*100:.0f}%" if rev else '—', ParagraphStyle('SR', fontSize=8, textColor=DARK_GREY, fontName='Helvetica', alignment=TA_RIGHT)),
                Paragraph(f"{hs:.0f}/100" if hs else 'N/A',  ParagraphStyle('SS', fontSize=8, textColor=hs_col, fontName='Helvetica-Bold', alignment=TA_RIGHT)),
            ])

        col_w = CONTENT_WIDTH / 4
        seg_tbl = Table(seg_rows, colWidths=[col_w * 1.8, col_w * 0.8, col_w * 0.6, col_w * 0.8])
        seg_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0),  NAVY),
            ('TEXTCOLOR',     (0, 0), (-1, 0),  WHITE),
            ('GRID',          (0, 0), (-1, -1), 0.3, MID_GREY),
            ('TOPPADDING',    (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING',   (0, 0), (-1, -1), 6),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
        ]))
        elements.append(seg_tbl)
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


    return elements
