"""
Tests for pse_quant.email
"""

from pathlib import Path
from pse_quant.email.sender import send_email, send_weekly_report


def test_send_email_mock_dev_mode():
    res = send_email(
        to="investor@example.com",
        subject="Test StockPilot",
        html_content="<p>Hello World</p>",
    )
    assert res["status"] == "mock_sent"
    assert res["to"] == ["investor@example.com"]


def test_send_weekly_report_mock(tmp_path):
    fake_pdf = tmp_path / "StockPilot_PH_Rankings_2026-11-04.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 mock content")

    top_stocks = [
        {"ticker": "DMC", "score": 85.0, "category": "Highest Quality", "mos_pct": 22.5},
        {"ticker": "AREIT", "score": 82.0, "category": "Highest Quality", "mos_pct": 18.0},
    ]

    res = send_weekly_report(
        to="subscriber@example.com",
        member_name="Josh",
        run_date="2026-11-04",
        pdf_path=fake_pdf,
        top_stocks=top_stocks,
    )
    assert res["status"] == "mock_sent"
    assert res["to"] == ["subscriber@example.com"]


def test_send_weekly_report_validation_and_empty_list(tmp_path):
    fake_pdf = tmp_path / "StockPilot_Empty.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 mock content")

    # 1. Empty top stocks works gracefully
    res = send_weekly_report(
        to="subscriber@example.com",
        member_name="Maria",
        pdf_path=fake_pdf,
        top_stocks=[],
    )
    assert res["status"] == "mock_sent"

    # 2. Invalid recipient email
    import pytest
    with pytest.raises(ValueError, match="Invalid recipient email"):
        send_weekly_report(to="bad-email", pdf_path=fake_pdf)

    # 3. Missing PDF file
    with pytest.raises(FileNotFoundError):
        send_weekly_report(to="sub@example.com", pdf_path=tmp_path / "nonexistent.pdf")
