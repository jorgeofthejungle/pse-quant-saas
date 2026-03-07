# ============================================================
# pdf_sentiment.py — Sentiment Panel & News Overview Section
# PSE Quant SaaS — reports sub-module
# ============================================================

from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from reports.pdf_styles import (
    NAVY, GOLD, GREEN, GREEN_LIGHT, RED, RED_LIGHT, ORANGE, ORANGE_LIGHT,
    LIGHT_GREY, MID_GREY, DARK_GREY, WHITE, BLACK,
    CONTENT_WIDTH,
)

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

    category  = sd.get('category', 'Neutral')
    score     = sd.get('score', 0.0)
    summary   = sd.get('summary', '')
    events    = sd.get('key_events') or []
    opp_flag  = sd.get('opportunistic_flag', 0)
    risk_flag = sd.get('risk_flag', 0)
    col       = SENTIMENT_COLORS.get(category, DARK_GREY)
    bg_col    = SENTIMENT_BGS.get(category, LIGHT_GREY)

    # Category badge + score bar
    bar_filled = min(10, max(0, int((score + 1) / 2 * 10)))
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
                               fontName='Helvetica-Bold', alignment=TA_CENTER)
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
