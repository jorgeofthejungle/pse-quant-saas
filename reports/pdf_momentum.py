# ============================================================
# pdf_momentum.py — Fundamental Momentum Analysis Panel
# PSE Quant SaaS — reports sub-module
# ============================================================
# Renders an in-depth momentum analysis section for each stock's
# detail page in the PDF report.
#
# What it shows:
#   1. Section header with brief intro
#   2. Per-signal table: Revenue, EPS, Operating CF
#      — Delta %, Direction label (ACCELERATING/STABLE/DECELERATING)
#      — Sub-score (0-100), Weight in composite
#   3. Combined momentum paragraph (plain English from explain_momentum())
#   4. Educational disclaimer
#
# Called from pdf_stock_detail_page.py after the score breakdown section.
# Only renders if momentum data exists in the stock's score breakdown.
# ============================================================

from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT

from reports.pdf_styles import (
    NAVY, GOLD, LIGHT_GREY, MID_GREY, DARK_GREY, WHITE, BLACK,
    GREEN, RED, ORANGE, BLUE,
    CONTENT_WIDTH,
)

# ── Direction label helpers ───────────────────────────────────

def _direction_label(delta, signal: str) -> tuple:
    """
    Returns (label_text, label_color) based on the delta value.
    Thresholds differ by signal type (revenue is smoother than EPS).
    """
    if delta is None:
        return 'N/A', DARK_GREY

    if signal == 'revenue':
        accel_thresh, decel_thresh = 2.0, -2.0
    elif signal == 'eps':
        accel_thresh, decel_thresh = 3.0, -3.0
    else:  # ocf uses percentage change
        accel_thresh, decel_thresh = 5.0, -5.0

    if delta >= accel_thresh:
        return 'ACCELERATING', GREEN
    elif delta <= decel_thresh:
        return 'DECELERATING', RED
    else:
        return 'STABLE', BLUE


def _fmt_delta(delta, signal: str) -> str:
    """Formats the delta value for display."""
    if delta is None:
        return 'N/A'
    unit = 'pp' if signal in ('revenue', 'eps') else '%'
    sign = '+' if delta >= 0 else ''
    return f"{sign}{delta:.1f}{unit}"


def _fmt_score(score) -> str:
    """Formats a sub-score (0-100) for display."""
    if score is None:
        return 'N/A'
    return f"{score:.0f}/100"


# ── Public API ────────────────────────────────────────────────

def build_momentum_panel(stock: dict, styles: dict) -> list:
    """
    Builds the Fundamental Momentum Analysis panel as a list of
    ReportLab flowables.

    Returns [] if no momentum data is available in the stock's breakdown.

    Parameters:
        stock  — full stock dict with 'score_breakdown' key
        styles — ParagraphStyle dict from pdf_generator (GoldLabel, ExplainText, etc.)
    """
    breakdown = stock.get('score_breakdown', {})
    mom_entry = breakdown.get('fundamental_momentum', {})
    mom_detail = mom_entry.get('value')

    # Momentum 'value' is the full detail dict (set in scorer.py)
    # Fall back to empty dict so N/A rows render rather than hiding the panel
    if not isinstance(mom_detail, dict):
        mom_detail = {}

    rev_delta  = mom_detail.get('rev_delta')
    eps_delta  = mom_detail.get('eps_delta')
    ocf_delta  = mom_detail.get('ocf_delta')
    rev_score  = mom_detail.get('rev_score')
    eps_score  = mom_detail.get('eps_score')
    ocf_score  = mom_detail.get('ocf_score')

    elements = []

    # ── Section header ────────────────────────────────────────
    elements.append(Spacer(1, 2 * mm))
    elements.append(Paragraph('FUNDAMENTAL MOMENTUM ANALYSIS', styles['GoldLabel']))
    elements.append(Paragraph(
        'Momentum measures whether this company\'s growth is SPEEDING UP or SLOWING DOWN. '
        'It compares the most recent years of performance to earlier years in the same '
        'company\'s own history — not against other stocks.',
        styles['ExplainText']
    ))
    elements.append(Spacer(1, 2 * mm))

    # ── Signal table ──────────────────────────────────────────
    # Header row
    hdr_style = ParagraphStyle(
        'MomHdr', fontSize=7.5, textColor=WHITE,
        fontName='Helvetica-Bold', alignment=TA_CENTER
    )
    col_style = ParagraphStyle(
        'MomCol', fontSize=8, textColor=BLACK, fontName='Helvetica'
    )
    col_bold = ParagraphStyle(
        'MomColB', fontSize=8, textColor=NAVY, fontName='Helvetica-Bold'
    )
    col_right = ParagraphStyle(
        'MomColR', fontSize=8, textColor=DARK_GREY,
        fontName='Helvetica', alignment=TA_RIGHT
    )

    signals = [
        ('Revenue Momentum',      rev_delta,  rev_score,  'revenue',  '40%'),
        ('EPS Momentum',          eps_delta,  eps_score,  'eps',      '35%'),
        ('Operating CF Momentum', ocf_delta,  ocf_score,  'ocf',      '25%'),
    ]

    table_data = [[
        Paragraph('SIGNAL',    hdr_style),
        Paragraph('DELTA',     hdr_style),
        Paragraph('DIRECTION', hdr_style),
        Paragraph('SCORE',     hdr_style),
        Paragraph('WEIGHT',    hdr_style),
    ]]

    for sig_name, delta, score, sig_type, weight in signals:
        dir_label, dir_color = _direction_label(delta, sig_type)
        table_data.append([
            Paragraph(sig_name, col_bold),
            Paragraph(_fmt_delta(delta, sig_type), col_right),
            Paragraph(dir_label, ParagraphStyle(
                'DirLbl', fontSize=8, textColor=dir_color,
                fontName='Helvetica-Bold', alignment=TA_CENTER
            )),
            Paragraph(_fmt_score(score), col_right),
            Paragraph(weight, ParagraphStyle(
                'Wt', fontSize=8, textColor=DARK_GREY,
                fontName='Helvetica', alignment=TA_CENTER
            )),
        ])

    col_widths = [50*mm, 22*mm, 42*mm, 24*mm, 18*mm]
    sig_table = Table(table_data, colWidths=col_widths)
    sig_table.setStyle(TableStyle([
        # Header row
        ('BACKGROUND',    (0, 0), (-1, 0),  NAVY),
        ('TEXTCOLOR',     (0, 0), (-1, 0),  WHITE),
        ('TOPPADDING',    (0, 0), (-1, 0),  5),
        ('BOTTOMPADDING', (0, 0), (-1, 0),  5),
        # Data rows
        ('BACKGROUND',    (0, 1), (-1, -1), LIGHT_GREY),
        ('ROWBACKGROUNDS',(0, 1), (-1, -1), [LIGHT_GREY, WHITE]),
        ('TOPPADDING',    (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
        # Grid
        ('GRID',          (0, 0), (-1, -1), 0.3, MID_GREY),
        ('LINEBELOW',     (0, 0), (-1, 0),  1.5, GOLD),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(KeepTogether([sig_table]))
    elements.append(Spacer(1, 3 * mm))

    # ── Combined momentum explanation ─────────────────────────
    try:
        from engine.scorer_momentum import explain_momentum
    except ImportError:
        from scorer_momentum import explain_momentum

    mom_text = explain_momentum(rev_delta, eps_delta, ocf_delta)
    if mom_text:
        exp_tbl = Table(
            [[Paragraph(mom_text, ParagraphStyle(
                'MomExp', fontSize=8, textColor=DARK_GREY,
                fontName='Helvetica-Oblique', leading=12
            ))]],
            colWidths=[CONTENT_WIDTH]
        )
        exp_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), WHITE),
            ('LEFTPADDING',   (0, 0), (-1, -1), 10),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
            ('TOPPADDING',    (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LINEBEFORE',    (0, 0), (0, -1),  3, GOLD),
            ('BOX',           (0, 0), (-1, -1), 0.3, MID_GREY),
        ]))
        elements.append(exp_tbl)
        elements.append(Spacer(1, 2 * mm))

    # ── Educational disclaimer ────────────────────────────────
    disclaimer = (
        'NOTE: Fundamental Momentum measures changes in business performance '
        '(revenue growth rate, earnings, cash flow) — NOT price momentum. '
        'Accelerating fundamentals suggest improving business conditions. '
        'Decelerating fundamentals may indicate a maturing growth phase or '
        'rising competitive pressure. Momentum is one factor in the composite score. '
        'Always review the full picture before making any investment decisions.'
    )
    disc_tbl = Table(
        [[Paragraph(disclaimer, ParagraphStyle(
            'MomDisc', fontSize=7, textColor=DARK_GREY,
            fontName='Helvetica-Oblique', leading=10
        ))]],
        colWidths=[CONTENT_WIDTH]
    )
    disc_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), LIGHT_GREY),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('BOX',           (0, 0), (-1, -1), 0.3, MID_GREY),
    ]))
    elements.append(disc_tbl)
    elements.append(Spacer(1, 3 * mm))

    return elements
