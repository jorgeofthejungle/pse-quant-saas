"""
Tests for pse_quant.reporting
"""

from pathlib import Path
from pse_quant.reporting.generator import generate_pdf_report


def test_generate_pdf_report(tmp_path):
    pdf_out = tmp_path / "StockPilot_Test_Report.pdf"

    ranked_stocks = [
        {
            "rank": 1,
            "ticker": "DMC",
            "sector": "Holding Firms",
            "score": 88.5,
            "category": "Highest Quality",
            "current_price": 11.50,
            "intrinsic_value": 14.80,
            "mos_pct": 22.3,
        },
        {
            "rank": 2,
            "ticker": "AREIT",
            "sector": "Property",
            "score": 82.0,
            "category": "Highest Quality",
            "current_price": 34.00,
            "intrinsic_value": 41.50,
            "mos_pct": 18.1,
        },
    ]

    generated_file = generate_pdf_report(
        ranked_stocks=ranked_stocks,
        output_path=pdf_out,
        run_date="2026-11-04",
        total_screened=245,
    )

    assert generated_file.exists()
    assert generated_file.stat().st_size > 1000
    with open(generated_file, "rb") as f:
        header = f.read(5)
        assert header == b"%PDF-"


def test_generate_pdf_report_empty_state_and_missing_data(tmp_path):
    pdf_out = tmp_path / "StockPilot_Empty_Report.pdf"

    # 1. Empty list
    empty_file = generate_pdf_report(
        ranked_stocks=[],
        output_path=pdf_out,
        run_date="2026-11-05",
        total_screened=0,
    )
    assert empty_file.exists()
    assert empty_file.stat().st_size > 1000

    # 2. Incomplete stock fields (None score, None price, None mos)
    partial_stocks = [
        {"ticker": "SMPH", "score": None, "mos_pct": None, "current_price": None, "intrinsic_value": None}
    ]
    partial_out = tmp_path / "StockPilot_Partial_Report.pdf"
    partial_file = generate_pdf_report(
        ranked_stocks=partial_stocks,
        output_path=partial_out,
        run_date="2026-11-05",
    )
    assert partial_file.exists()
    assert partial_file.stat().st_size > 1000
