"""
pse_quant.reporting — PDF Report generation package
"""

from pse_quant.reporting.generator import generate_pdf_report
from pse_quant.reporting.styles import get_report_stylesheet

__all__ = ["generate_pdf_report", "get_report_stylesheet"]
