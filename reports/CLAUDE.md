# reports/CLAUDE.md — PDF Report Generation Implementation Details
> See root CLAUDE.md for system rules, stock data format, DB schema, and architecture.
> This file covers reports-specific implementation details only.

All PDF generation uses ReportLab. PDFs save to `~/Desktop/` (resolved via `os.path.expanduser`; in WSL2 this is `/home/jorgeofthejungle/Desktop/`).

---

## reports/pdf_styles.py
Color palette, page constants, and shared style helpers. Registers the Inter font family (Regular/Bold/Italic) from `assets/fonts/`. Exports: color constants (`NAVY`, `GOLD`, `GREEN`, etc.), `CONTENT_WIDTH`, `score_color`, `score_bg`, `grade`, `grade_label`, `mos_signal`, `get_stock_profiles`, `BarChartIcon`, `PORTFOLIO_EXPLAIN`, `MOS_EXPLAIN`.

## reports/pdf_cover_page.py
Builds the cover hero panel and the full disclaimer page. Key functions: `build_cover_page(portfolio_name, run_date)`, `build_disclaimer_page()`.

## reports/pdf_rankings_table.py
Renders the ranked stock table and per-stock overall assessment callout. Key function: `generate_overall_assessment(stock)` → ReportLab flowables. Also exports the rankings table builder used by `pdf_generator.py`.

## reports/pdf_stock_detail_page.py
Builds the per-stock detail page (metrics, MoS bar, score breakdown, sentiment). Calls `generate_overall_assessment()` from `pdf_rankings_table`. Entry: `build_stock_detail_page(stock, portfolio_type)`.

## reports/pdf_portfolio_sections.py
Renders the per-portfolio (Dividend / Value) ranked stock sections within the PDF.

## reports/pdf_sentiment.py
Renders the sentiment panel when `sentiment` data is present on ranked stocks.

## reports/pdf_generator.py (facade)
Function: `generate_report(portfolio_type, ranked_stocks, output_path, total_stocks_screened)`
Orchestrates: cover → rankings table → per-stock detail pages → disclaimer. Includes sentiment panel when data is present.

---

## 7A. EDUCATIONAL COMMUNICATION LAYER — REPORT WRITING STANDARD

All PDF explanations, stock summaries, breakdown text, and Discord embed content must follow this framework.

### Role when writing report text
Senior investment learning designer — not a salesperson, not a promoter.

### Writing style
1. Simple language. Short sentences.
2. Explain financial terms immediately in plain English.
3. Never assume prior investing knowledge.
4. Always explain both strengths and risks.
5. Never promise returns. Never imply a recommendation.

### Tone
Calm, analytical, neutral, beginner-friendly, rational, professional.

### Key term definitions
- P/E: "You are paying ₱X for every ₱1 the company earns per year."
- ROE: "This measures how efficiently management uses shareholders' money."
- D/E: "This shows how much the company relies on borrowed money."
- MoS: "Discount between intrinsic value and current price. Larger = more cushion."
- Intrinsic Value: "Mathematical estimate of fair business value. Not a price prediction."

### Priority hierarchy
Clarity > Complexity | Education > Jargon | Risk > Optimism | Neutrality > Persuasion
