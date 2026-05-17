# ============================================================
# pdf_rankings_table.py — Rankings Table & Overall Assessment
# PSE Quant SaaS — reports sub-module
# ============================================================

from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT

from reports.pdf_styles import (
    NAVY, GOLD, GREEN, ORANGE, RED, BLUE,
    LIGHT_GREY, MID_GREY, DARK_GREY, WHITE, BLACK,
    CONTENT_WIDTH, MOS_EXPLAIN,
    score_color, score_bg, grade, grade_label, mos_signal,
)


_SIG_HEX = {
    'DEEP DISCOUNT':  '#27AE60',
    'DISCOUNTED':     '#2471A3',
    'FAIRLY VALUED':  '#E67E22',
    'ABOVE ESTIMATE': '#E74C3C',
}


def _score_hex(sc: float) -> str:
    if sc >= 75:   return '#27AE60'
    elif sc >= 55: return '#2471A3'
    elif sc >= 40: return '#E67E22'
    else:          return '#E74C3C'


def _score_bar(sc: float, blocks: int = 10) -> str:
    filled = max(0, min(blocks, round(sc / 100 * blocks)))
    return '▓' * filled + '░' * (blocks - filled)


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
        'TH', fontSize=9, textColor=WHITE,
        fontName='Inter-Bold', alignment=TA_CENTER, leading=13,
    )
    td = ParagraphStyle(
        'TD', fontSize=9, textColor=BLACK,
        fontName='Inter-Regular', alignment=TA_CENTER, leading=12,
    )
    td_left = ParagraphStyle(
        'TDLeft', fontSize=9, textColor=BLACK,
        fontName='Inter-Regular', alignment=TA_LEFT, leading=11,
    )

    # ── 5-column layout — content width 174mm ─────────────
    if portfolio_type == 'dividend':
        headers = ['#', 'Ticker / Company', 'Score', 'Yield / CAGR', 'MoS% · Signal']
        col_w   = [6*mm, 64*mm, 36*mm, 32*mm, 36*mm]
    elif portfolio_type == 'value':
        headers = ['#', 'Ticker / Company', 'Score', 'P/E · ROE', 'MoS% · Signal']
        col_w   = [6*mm, 64*mm, 36*mm, 32*mm, 36*mm]
    elif portfolio_type == 'unified':
        headers = ['#', 'Ticker / Company', 'Score', 'Hlth · Impr · Prst', 'MoS% · Signal']
        col_w   = [6*mm, 57*mm, 36*mm, 45*mm, 30*mm]
    else:
        headers = ['#', 'Ticker / Company', 'Score', 'Yield · P/E', 'MoS% · Signal']
        col_w   = [6*mm, 64*mm, 36*mm, 32*mm, 36*mm]

    header_row = [Paragraph(h, th) for h in headers]
    data_rows  = [header_row]

    for i, stock in enumerate(ranked_stocks):
        sc     = stock.get('score', 0)
        mp     = stock.get('mos_pct', None)
        sig    = mos_signal(mp)
        ticker = stock.get('ticker', '')
        name   = stock.get('name', '') or ''
        name_s = (name[:34] + '…') if len(name) > 34 else name

        # Col 1: rank
        c_rank = Paragraph(str(i + 1), td)

        # Col 2: ticker (bold) + company name (small, grey) — two lines
        c_ticker = Paragraph(
            f'<b>{ticker}</b><br/>'
            f'<font size="7" color="#566573">{name_s}</font>',
            td_left,
        )

        # Col 3: score number + unicode color bar below
        hex_s = _score_hex(sc)
        c_score = Paragraph(
            f'<font color="{hex_s}"><b>{sc:.0f}/100</b></font><br/>'
            f'<font size="7" color="{hex_s}">{_score_bar(sc)}</font>',
            td,
        )

        # Col 4: portfolio-specific metric pair
        if portfolio_type == 'dividend':
            dy   = stock.get('dividend_yield') or 0
            cagr = stock.get('dividend_cagr_5y') or 0
            c_metric = Paragraph(
                f'<b>{dy:.1f}%</b><br/>'
                f'<font size="7" color="#566573">CAGR +{cagr:.1f}%/yr</font>',
                td,
            )
        elif portfolio_type == 'value':
            pe  = stock.get('pe') or 0
            roe = stock.get('roe') or 0
            c_metric = Paragraph(
                f'<b>{pe:.1f}x</b><br/>'
                f'<font size="7" color="#566573">ROE {roe:.1f}%</font>',
                td,
            )
        elif portfolio_type == 'unified':
            layers = stock.get('breakdown', {}).get('layers', {})
            h_s = layers.get('health',      {}).get('score')
            i_s = layers.get('improvement', {}).get('score')
            p_s = layers.get('persistence', {}).get('score')
            def _ls(v): return f'{v:.0f}' if v is not None else '—'
            c_metric = Paragraph(
                f'<font color="{_score_hex(h_s or 0)}"><b>{_ls(h_s)}</b></font>'
                f' · '
                f'<font color="{_score_hex(i_s or 0)}"><b>{_ls(i_s)}</b></font>'
                f' · '
                f'<font color="{_score_hex(p_s or 0)}"><b>{_ls(p_s)}</b></font>',
                td,
            )
        else:
            dy = stock.get('dividend_yield') or 0
            pe = stock.get('pe') or 0
            c_metric = Paragraph(f'{dy:.1f}% · {pe:.1f}x', td)

        # Col 5: MoS% (colored bold) + signal label below
        mos_str = f'{mp:.1f}%' if mp is not None else 'N/A'
        hex_m   = '#27AE60' if (mp is not None and mp >= 15) else \
                  '#E67E22' if (mp is not None and mp >= 0)  else \
                  '#E74C3C' if mp is not None else '#566573'
        hex_sig = _SIG_HEX.get(sig, '#566573')
        c_mos = Paragraph(
            f'<font color="{hex_m}"><b>{mos_str}</b></font><br/>'
            f'<font size="7" color="{hex_sig}">{sig}</font>',
            td,
        )

        data_rows.append([c_rank, c_ticker, c_score, c_metric, c_mos])

    tbl = Table(data_rows, colWidths=col_w, repeatRows=1)
    tbl_style = [
        ('BACKGROUND',    (0, 0), (-1, 0),  NAVY),
        ('TEXTCOLOR',     (0, 0), (-1, 0),  WHITE),
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN',         (1, 1), (1, -1),  'LEFT'),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE',      (0, 0), (-1, -1), 9),
        ('TOPPADDING',    (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING',   (1, 1), (1, -1),  4),
        ('GRID',          (0, 0), (-1, -1), 0.3, MID_GREY),
        ('LINEBELOW',     (0, 0), (-1, 0),  1.5, GOLD),
    ]
    for i in range(1, len(data_rows)):
        bg = LIGHT_GREY if i % 2 == 0 else WHITE
        tbl_style.append(('BACKGROUND', (0, i), (-1, i), bg))

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
    ocf  = stock.get('operating_cf',      None)

    positive_years = sum(1 for n in ni3 if n > 0)

    # Cash Flow Quality ratio
    _ni_latest = ni3[0] if ni3 and ni3[0] else None
    cf_quality_ratio = round(ocf / abs(_ni_latest), 2) if (ocf is not None and _ni_latest and _ni_latest != 0) else None

    # Earnings Yield vs Bond Rate (for value)
    _bond_rate = 6.5
    ey_spread = round((1 / pe) * 100 - _bond_rate, 1) if pe and pe > 0 else None

    if portfolio_type == 'dividend':
        if dy >= 7:
            strengths.append(
                f"a high dividend yield of {dy:.1f}%. "
                f"For every PHP 100 you invest, you earn PHP {dy:.2f} per year in cash income"
            )
        elif dy >= 5:
            strengths.append(
                f"a solid dividend yield of {dy:.1f}%, which is above the PSE average "
                f"and provides meaningful passive income"
            )
        elif dy >= 3:
            concerns.append(
                f"a modest yield of {dy:.1f}%, which is below the typical income "
                f"investor target of 5%. Income generation may be limited"
            )
        else:
            concerns.append(
                f"a low dividend yield of {dy:.1f}%. This is a weak income candidate "
                f"for investors seeking regular cash payouts"
            )

        if pr and 30 <= pr <= 70:
            strengths.append(
                f"a healthy payout ratio of {pr:.1f}%. The company rewards shareholders "
                f"well while keeping enough profit to reinvest in the business"
            )
        elif pr and pr > 85:
            concerns.append(
                f"a high payout ratio of {pr:.1f}%, which leaves very little room for error. "
                f"Any drop in earnings could put the dividend at risk"
            )

        if fcf >= 1.5:
            strengths.append(
                f"strong free cash flow coverage of {fcf:.1f}x. The dividend is backed "
                f"by real cash generated by the business, not just accounting profit"
            )
        elif 0 < fcf < 1.0:
            concerns.append(
                f"free cash flow coverage of only {fcf:.1f}x. The company is not generating "
                f"enough cash to fully fund the dividends it is paying out"
            )

        if cagr >= 5:
            strengths.append(
                f"dividend growth of {cagr:.1f}% per year over the past 5 years. "
                f"Shareholders have been receiving a steadily rising income stream"
            )
        elif cagr < 0:
            concerns.append(
                f"a shrinking dividend track record (CAGR of {cagr:.1f}% per year "
                f"over 5 years). The income from this stock has been declining"
            )

        # Cash Flow Quality for dividend portfolios
        if cf_quality_ratio is not None:
            if cf_quality_ratio >= 1.1:
                strengths.append(
                    f"strong cash flow quality of {cf_quality_ratio:.2f}x. For every PHP 1 "
                    f"of reported profit, the company generates PHP {cf_quality_ratio:.2f} "
                    f"in actual cash. The earnings are real and the dividend is credible"
                )
            elif cf_quality_ratio < 0.7:
                concerns.append(
                    f"a low cash flow quality ratio of {cf_quality_ratio:.2f}x. Reported "
                    f"earnings are significantly higher than actual cash collected from "
                    f"operations. This gap deserves scrutiny before trusting the dividend"
                )

    if portfolio_type == 'dividend':
        # Growth Consistency for dividend portfolio
        revenue_5y = stock.get('revenue_5y', [])
        if len(revenue_5y) >= 3:
            valid_rev = [r for r in revenue_5y if r and r > 0]
            if len(valid_rev) >= 3:
                import statistics as _st
                mean_r = sum(valid_rev) / len(valid_rev)
                if mean_r > 0:
                    cv = _st.pstdev(valid_rev) / mean_r
                    if cv <= 0.20:
                        strengths.append(
                            f"highly consistent revenue growth (variation coefficient {cv:.2f}). "
                            f"Steady, predictable revenue makes future dividend increases "
                            f"far more reliable"
                        )
                    elif cv > 0.50:
                        concerns.append(
                            f"erratic revenue growth (variation coefficient {cv:.2f}). "
                            f"The boom-and-bust pattern makes it harder to count on "
                            f"sustained dividend increases year after year"
                        )

    if portfolio_type == 'value':
        if pe and pe <= 10:
            strengths.append(
                f"a low P/E ratio of {pe:.1f}x. You are paying only PHP {pe:.1f} "
                f"for every PHP 1 the company earns per year. By PSE standards, "
                f"this looks inexpensive"
            )
        elif pe and pe >= 25:
            concerns.append(
                f"a high P/E ratio of {pe:.1f}x. The market is pricing in strong "
                f"future growth. If that growth does not materialise, the stock "
                f"could disappoint"
            )

        if pb and pb <= 1.0:
            strengths.append(
                f"a Price-to-Book ratio of {pb:.2f}x. You are buying the company's "
                f"assets for less than their stated book value on the balance sheet"
            )
        elif pb and pb > 2.5:
            concerns.append(
                f"a high Price-to-Book ratio of {pb:.2f}x. You are paying a significant "
                f"premium over the company's net asset value. This requires the "
                f"business to keep performing strongly to justify the price"
            )

        if rev >= 10:
            strengths.append(
                f"revenue growing at {rev:.1f}% per year, which is well ahead of "
                f"inflation and signals a business that is expanding"
            )
        elif rev < 0:
            concerns.append(
                f"declining revenue (CAGR of {rev:.1f}% per year). A shrinking "
                f"top line is a warning sign that the business may be losing ground"
            )

        # Earnings Yield vs Bond Rate for value stocks
        if ey_spread is not None:
            ey_val = round((1 / pe) * 100, 1) if pe and pe > 0 else None
            if ey_spread >= 5 and ey_val:
                strengths.append(
                    f"an earnings yield of {ey_val:.1f}% which is {ey_spread:.1f}% above "
                    f"the PH 10Y bond rate of {_bond_rate}%. You are being well compensated "
                    f"for the extra risk of owning this stock over a government bond"
                )
            elif ey_spread < 0:
                concerns.append(
                    f"an earnings yield of {ey_val:.1f}% which is BELOW the "
                    f"PH 10Y bond rate of {_bond_rate}%. A risk-free government bond "
                    f"currently pays more than this stock earns per peso of price"
                )

        # Cash Flow Quality for value stocks
        if cf_quality_ratio is not None:
            if cf_quality_ratio >= 1.1:
                strengths.append(
                    f"strong cash flow quality of {cf_quality_ratio:.2f}x, confirming "
                    f"that reported profits are backed by real cash from operations"
                )
            elif cf_quality_ratio < 0.7:
                concerns.append(
                    f"a low cash flow quality ratio of {cf_quality_ratio:.2f}x. "
                    f"Reported earnings are not fully converting into real operating cash"
                )

    # ROE and debt apply to all portfolios
    if roe >= 15:
        strengths.append(
            f"an ROE of {roe:.1f}%. Management is generating strong returns on "
            f"shareholder capital. Our rule-based model prioritizes 15% and above as a quality threshold"
        )
    elif roe < 8:
        concerns.append(
            f"a below-average ROE of {roe:.1f}%. The business earns poor returns "
            f"on the money shareholders have invested in it"
        )

    if de <= 0.5:
        strengths.append(
            f"a low debt-to-equity ratio of {de:.2f}x. The company is largely "
            f"self-funded, which makes it more resilient during periods of rising "
            f"interest rates or economic stress"
        )
    elif de > 2.0:
        concerns.append(
            f"high leverage at {de:.2f}x debt to equity. A heavily borrowed "
            f"company faces greater risk during economic downturns or when "
            f"interest rates rise"
        )

    if positive_years == 3:
        strengths.append(
            "consistent profitability across all 3 of the past 3 years, "
            "which shows a stable and reliable earnings base"
        )
    elif positive_years < 3:
        concerns.append(
            f"only {positive_years} profitable year(s) out of the last 3. "
            f"Inconsistent earnings make it harder to predict whether dividends "
            f"or growth targets can be sustained"
        )

    # Unified: use 3-layer breakdown for the assessment text
    if portfolio_type == 'unified':
        breakdown = stock.get('breakdown', {})
        layers    = breakdown.get('layers', {})
        category  = breakdown.get('category', '')
        h_s = layers.get('health',      {}).get('score', 0) or 0
        i_s = layers.get('improvement', {}).get('score', 0) or 0
        p_s = layers.get('persistence', {}).get('score', 0) or 0

        u_lines = [f"{ticker} earns a unified score of {score:.0f}/100 "
                   f"and is classified as: {category}."]
        u_str = []
        u_con = []

        if h_s >= 70:
            u_str.append(f"strong financial health ({h_s:.0f}/100)")
        elif h_s < 45:
            u_con.append(f"below-average financial health ({h_s:.0f}/100)")

        if i_s >= 65:
            u_str.append(f"clearly improving fundamentals ({i_s:.0f}/100)")
        elif i_s < 40:
            u_con.append(f"limited fundamental improvement ({i_s:.0f}/100)")

        if p_s >= 70:
            u_str.append(f"highly consistent multi-year improvement ({p_s:.0f}/100)")
        elif p_s < 40:
            u_con.append(f"inconsistent track record ({p_s:.0f}/100)")

        if u_str:
            u_lines.append(f"Strengths: {'; '.join(u_str)}.")
        if u_con:
            u_lines.append(f"Areas of concern: {'; '.join(u_con)}.")

        iv = stock.get('intrinsic_value')
        cp = stock.get('current_price')
        mp = stock.get('mos_pct')
        if iv and cp and mp is not None:
            if mp >= 15:
                u_lines.append(
                    f"At PHP {cp:.2f}, this stock trades {mp:.1f}% below our intrinsic "
                    f"value estimate of PHP {iv:.2f} — a meaningful margin of safety."
                )
            elif mp >= 0:
                u_lines.append(
                    f"At PHP {cp:.2f}, the stock is near our intrinsic value estimate of "
                    f"PHP {iv:.2f}. It appears fairly priced at current levels."
                )
            else:
                u_lines.append(
                    f"At PHP {cp:.2f}, the stock trades {abs(mp):.1f}% ABOVE our intrinsic "
                    f"value estimate of PHP {iv:.2f}. Patient investors may prefer to wait."
                )
        return "  ".join(u_lines)

    _display = {
        'dividend': 'Dividend',
        'value':    'Value',
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
                f"At PHP {cp:.2f}, this stock is trading {mp:.1f}% below our calculated "
                f"intrinsic value of PHP {iv:.2f}. That gap represents a meaningful "
                f"margin of safety for long-term investors."
            )
        elif mp >= 0:
            lines.append(
                f"At PHP {cp:.2f}, this stock is trading close to our intrinsic value "
                f"estimate of PHP {iv:.2f}. It appears fairly priced but is not offering "
                f"a deep discount at this level."
            )
        else:
            lines.append(
                f"At PHP {cp:.2f}, this stock is trading {abs(mp):.1f}% ABOVE our "
                f"intrinsic value estimate of PHP {iv:.2f}. Patient investors may want "
                f"to wait for a lower price before considering a position."
            )

    return "  ".join(lines)
