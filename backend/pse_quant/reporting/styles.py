"""
pse_quant/reporting/styles.py — Typography, Color Palette & ReportLab Styling
Registers Inter font family and provides consistent visual styles for StockPilot PH reports.
"""

from __future__ import annotations
import os
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping

# ── Font Registration ─────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_FONTS_DIR = _ROOT / "assets" / "fonts"

if _FONTS_DIR.exists() and (_FONTS_DIR / "Inter-Regular.ttf").exists():
    try:
        pdfmetrics.registerFont(TTFont("Inter-Regular", str(_FONTS_DIR / "Inter-Regular.ttf")))
        pdfmetrics.registerFont(TTFont("Inter-Bold", str(_FONTS_DIR / "Inter-Bold.ttf")))
        pdfmetrics.registerFont(TTFont("Inter-Italic", str(_FONTS_DIR / "Inter-Italic.ttf")))
        
        pdfmetrics.registerFontFamily(
            "Inter",
            normal="Inter-Regular",
            bold="Inter-Bold",
            italic="Inter-Italic",
            boldItalic="Inter-Bold",
        )
        addMapping("Inter", 0, 0, "Inter-Regular")
        addMapping("Inter", 1, 0, "Inter-Bold")
        addMapping("Inter", 0, 1, "Inter-Italic")
        addMapping("Inter", 1, 1, "Inter-Bold")

        DEFAULT_FONT = "Inter-Regular"
        DEFAULT_BOLD = "Inter-Bold"
    except Exception:
        DEFAULT_FONT = "Helvetica"
        DEFAULT_BOLD = "Helvetica-Bold"
else:
    DEFAULT_FONT = "Helvetica"
    DEFAULT_BOLD = "Helvetica-Bold"

# ── Brand Color Palette ───────────────────────────────────────
NAVY = colors.HexColor("#0D1F3C")
NAVY_LIGHT = colors.HexColor("#1A3564")
GOLD = colors.HexColor("#F0A500")
GOLD_LIGHT = colors.HexColor("#FDF3DC")
GREEN = colors.HexColor("#16A34A")
GREEN_LIGHT = colors.HexColor("#DCFCE7")
RED = colors.HexColor("#DC2626")
RED_LIGHT = colors.HexColor("#FEE2E2")
BLUE = colors.HexColor("#2563EB")
BLUE_LIGHT = colors.HexColor("#DBEAFE")
ORANGE = colors.HexColor("#EA580C")
ORANGE_LIGHT = colors.HexColor("#FFEDD5")
LIGHT_GREY = colors.HexColor("#F8FAFC")
BORDER_GREY = colors.HexColor("#E2E8F0")
DARK_GREY = colors.HexColor("#64748B")
WHITE = colors.white
BLACK = colors.HexColor("#0F172A")

# ── Page Geometry ─────────────────────────────────────────────
PAGE_WIDTH, PAGE_HEIGHT = A4
LEFT_MARGIN = 16 * mm
RIGHT_MARGIN = 16 * mm
TOP_MARGIN = 16 * mm
BOTTOM_MARGIN = 16 * mm
CONTENT_WIDTH = PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN


def get_report_stylesheet():
    """Builds a typed ReportLab stylesheet using Inter typography."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        "ReportTitle",
        fontName=DEFAULT_BOLD,
        fontSize=24,
        leading=28,
        textColor=NAVY,
        alignment=TA_LEFT,
    ))

    styles.add(ParagraphStyle(
        "ReportSubtitle",
        fontName=DEFAULT_FONT,
        fontSize=12,
        leading=16,
        textColor=DARK_GREY,
        alignment=TA_LEFT,
    ))

    styles.add(ParagraphStyle(
        "SectionHeader",
        fontName=DEFAULT_BOLD,
        fontSize=14,
        leading=18,
        textColor=NAVY,
        spaceBefore=12,
        spaceAfter=6,
    ))

    styles.add(ParagraphStyle(
        "BodySmall",
        fontName=DEFAULT_FONT,
        fontSize=9,
        leading=13,
        textColor=BLACK,
    ))

    styles.add(ParagraphStyle(
        "DisclaimerText",
        fontName=DEFAULT_FONT,
        fontSize=8,
        leading=11,
        textColor=DARK_GREY,
    ))

    return styles
