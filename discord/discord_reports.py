# ============================================================
# discord_reports.py — Portfolio PDF Report Delivery
# PSE Quant SaaS
# ============================================================

import os
from datetime import datetime
from discord.discord_core import (
    _post_webhook, _post_webhook_with_file,
    PORTFOLIO_COLOURS, PORTFOLIO_EMOJI, DISCLAIMER, MAX_FILE_BYTES,
)


def send_report(
    webhook_url:    str,
    pdf_path:       str,
    portfolio_type: str,
    ranked_stocks:  list,
    run_date:       str = None,
) -> bool:
    """
    Sends a portfolio PDF report to a Discord channel.

    Parameters:
        webhook_url     — Discord webhook URL for the target channel
        pdf_path        — Absolute path to the generated PDF file
        portfolio_type  — 'pure_dividend', 'dividend_growth', or 'value'
        ranked_stocks   — List of scored stock dicts (from process_stocks)
        run_date        — Optional date string; defaults to today

    What gets sent:
        1. An embed with the top 5 ranked stocks (scores, key metrics, MoS)
        2. The PDF file as an attachment (if under 8 MB)
           If the PDF is too large, a text note is sent instead.

    Returns True if Discord accepted the message, False otherwise.
    """
    if run_date is None:
        run_date = datetime.now().strftime('%B %d, %Y')

    emoji      = PORTFOLIO_EMOJI.get(portfolio_type, '📋')
    colour     = PORTFOLIO_COLOURS.get(portfolio_type, 0x1B4B6B)
    port_upper = portfolio_type.upper()

    # ── Build the top-5 fields ──
    fields = []
    for i, stock in enumerate(ranked_stocks[:5]):
        sc        = stock.get('score', 0)
        ticker    = stock.get('ticker', '')
        mos_pct   = stock.get('mos_pct', None)
        mos_price = stock.get('mos_price', None)
        dy        = stock.get('dividend_yield', None)
        pe        = stock.get('pe', None)

        if portfolio_type == 'pure_dividend':
            metric_line = f"Yield: {dy:.1f}%" if dy else "Yield: N/A"
        elif portfolio_type == 'dividend_growth':
            cagr  = stock.get('dividend_cagr_5y', None)
            parts = []
            if dy:
                parts.append(f"Yield: {dy:.1f}%")
            if cagr:
                parts.append(f"CAGR: +{cagr:.1f}%/yr")
            metric_line = "  |  ".join(parts) if parts else "N/A"
        elif portfolio_type == 'value':
            metric_line = f"P/E: {pe:.1f}x" if pe else "P/E: N/A"
        else:
            metric_line = "N/A"

        mos_line = (
            f"MoS: {mos_pct:.1f}%  |  Buy <= PHP{mos_price:.2f}"
            if mos_pct is not None and mos_price else "MoS: N/A"
        )

        grade_str = (
            'A - STRONG' if sc >= 80 else
            'B - GOOD'   if sc >= 65 else
            'C - FAIR'   if sc >= 50 else
            'D - WEAK'
        )

        fields.append({
            'name':   f"#{i+1}  {ticker}  --  {sc}/100  [{grade_str}]",
            'value':  f"{metric_line}\n{mos_line}",
            'inline': False,
        })

    embed = {
        'title':       f"{emoji}  PSE {port_upper} PORTFOLIO REPORT",
        'description': f"**Run date:** {run_date}\n**Stocks ranked:** {len(ranked_stocks)}",
        'color':       colour,
        'fields':      fields,
        'footer':      {'text': DISCLAIMER},
    }

    payload = {'embeds': [embed]}

    if os.path.exists(pdf_path):
        file_size = os.path.getsize(pdf_path)
        if file_size <= MAX_FILE_BYTES:
            print(f"Sending {portfolio_type} report to Discord with PDF attachment...")
            success = _post_webhook_with_file(webhook_url, pdf_path, payload)
        else:
            size_mb = file_size / (1024 * 1024)
            embed['fields'].append({
                'name':   'PDF Not Attached',
                'value':  (
                    f"The report PDF is {size_mb:.1f} MB -- above Discord's 8 MB limit. "
                    f"The file is saved locally at:\n`{pdf_path}`"
                ),
                'inline': False,
            })
            print(f"PDF too large ({size_mb:.1f} MB) -- sending embed only.")
            success = _post_webhook(webhook_url, payload)
    else:
        embed['fields'].append({
            'name':   'PDF Not Found',
            'value':  f"Expected at: `{pdf_path}`",
            'inline': False,
        })
        print(f"PDF not found at {pdf_path} -- sending embed only.")
        success = _post_webhook(webhook_url, payload)

    if success:
        print(f"Discord delivery complete: #{portfolio_type} report sent.")
    return success
