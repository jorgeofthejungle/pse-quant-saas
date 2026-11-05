"""
pse_quant/email/sender.py — Email Distribution Engine
Delivers PDF research reports, morning digests, and alerts to members.
Uses Resend API (with local dev fallback logging when API key is unset).
"""

from __future__ import annotations
import base64
import json
import logging
from pathlib import Path
from typing import Any
import requests

from pse_quant.config import RESEND_API_KEY, EMAIL_FROM

logger = logging.getLogger("pse_quant.email")
RESEND_ENDPOINT = "https://api.resend.com/emails"


def send_email(
    to: str | list[str],
    subject: str,
    html_content: str,
    attachments: list[dict[str, str]] | None = None,
    reply_to: str | None = None,
) -> dict[str, Any]:
    """
    Sends an email via Resend.
    attachments format: [{'filename': 'report.pdf', 'content': base64_str_or_bytes}]

    In development (or when RESEND_API_KEY is not configured), logs the email and returns a mock success.
    """
    recipients = [to] if isinstance(to, str) else to

    if not RESEND_API_KEY:
        logger.info(
            f"[DEV EMAIL MOCK] To: {recipients} | Subject: '{subject}' | Attachments: {len(attachments or [])}"
        )
        return {
            "id": "mock_email_dev_id",
            "to": recipients,
            "subject": subject,
            "status": "mock_sent",
        }

    # Format attachments for Resend
    formatted_attachments = []
    if attachments:
        for att in attachments:
            content = att.get("content")
            if isinstance(content, bytes):
                content = base64.b64encode(content).decode("utf-8")
            formatted_attachments.append({
                "filename": att.get("filename", "attachment"),
                "content": content,
            })

    payload = {
        "from": EMAIL_FROM,
        "to": recipients,
        "subject": subject,
        "html": html_content,
    }
    if formatted_attachments:
        payload["attachments"] = formatted_attachments
    if reply_to:
        payload["reply_to"] = reply_to

    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json",
    }

    resp = requests.post(RESEND_ENDPOINT, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def send_weekly_report(
    to: str | None = None,
    member_name: str = "Investor",
    run_date: str | None = None,
    pdf_path: str | Path | None = None,
    top_stocks: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Sends the weekly StockPilot PH PDF report to a subscriber."""
    from datetime import date
    recipient = to or kwargs.get("to_email") or kwargs.get("recipient")
    if not recipient:
        raise ValueError("Recipient email address must be provided.")

    file_path = pdf_path or kwargs.get("pdf_attachment_path")
    if not file_path:
        raise ValueError("PDF report path must be provided.")

    pdf_file = Path(file_path)
    if not pdf_file.exists():
        raise FileNotFoundError(f"PDF report not found at {pdf_file}")

    if run_date is None:
        run_date = date.today().isoformat()

    if top_stocks is None:
        top_stocks = kwargs.get("top_stocks") or []

    with open(pdf_file, "rb") as f:
        pdf_bytes = f.read()

    stock_rows_html = "".join([
        f"""<tr>
            <td style="padding: 8px; border-bottom: 1px solid #e2e8f0; font-weight: bold;">#{s.get('rank', i+1)} {s.get('ticker')}</td>
            <td style="padding: 8px; border-bottom: 1px solid #e2e8f0;">{s.get('score', 0):.1f}</td>
            <td style="padding: 8px; border-bottom: 1px solid #e2e8f0;">{s.get('category', 'Quality')}</td>
            <td style="padding: 8px; border-bottom: 1px solid #e2e8f0; color: #16a34a; font-weight: bold;">
                {s.get('mos_pct', 0.0):+.1f}%
            </td>
        </tr>"""
        for i, s in enumerate(top_stocks[:5])
    ])

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; padding: 24px;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; border: 1px solid #e2e8f0;">
            <div style="background-color: #0f172a; padding: 24px; text-align: center;">
                <h1 style="color: #ffffff; margin: 0; font-size: 24px; letter-spacing: -0.5px;">StockPilot PH</h1>
                <p style="color: #94a3b8; margin: 4px 0 0 0; font-size: 14px;">Philippine Equity Quantitative Rankings • {run_date}</p>
            </div>
            <div style="padding: 24px;">
                <p style="font-size: 16px; color: #334155; margin-top: 0;">Hi {member_name or 'there'},</p>
                <p style="font-size: 15px; color: #475569; line-height: 1.5;">
                    The latest Philippine Stock Exchange quantitative rankings report has been generated.
                    Your complete research report is attached as a PDF (<strong>{pdf_file.name}</strong>).
                </p>

                <h3 style="color: #0f172a; font-size: 16px; border-bottom: 2px solid #0f172a; padding-bottom: 6px; margin-top: 24px;">
                    Top 5 Ranked Equities Today
                </h3>
                <table style="width: 100%; border-collapse: collapse; font-size: 14px; text-align: left;">
                    <thead>
                        <tr style="background-color: #f1f5f9; color: #475569;">
                            <th style="padding: 8px;">Ticker</th>
                            <th style="padding: 8px;">Score</th>
                            <th style="padding: 8px;">Quality Band</th>
                            <th style="padding: 8px;">Margin of Safety</th>
                        </tr>
                    </thead>
                    <tbody>
                        {stock_rows_html}
                    </tbody>
                </table>

                <div style="margin-top: 32px; padding: 16px; background-color: #f8fafc; border-radius: 6px; border-left: 4px solid #3b82f6;">
                    <p style="margin: 0; font-size: 13px; color: #64748b; line-height: 1.4;">
                        <strong>Educational Notice:</strong> Intrinsic value and Margin of Safety computations are mathematical reference figures derived from fundamental ratios. They are not price targets, buy/sell recommendations, or investment advice.
                    </p>
                </div>
            </div>
            <div style="background-color: #f1f5f9; padding: 16px; text-align: center; font-size: 12px; color: #94a3b8;">
                © {run_date[:4]} StockPilot PH • <a href="https://stockpilot.ph" style="color: #2563eb; text-decoration: none;">Member Portal</a>
            </div>
        </div>
    </body>
    </html>
    """

    return send_email(
        to=recipient,
        subject=f"📊 StockPilot PH Rankings Report — {run_date}",
        html_content=html,
        attachments=[{
            "filename": pdf_file.name,
            "content": pdf_bytes,
        }],
    )
