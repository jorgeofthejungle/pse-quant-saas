# reports/CLAUDE.md — PDF Report Generation Implementation Details
> See root CLAUDE.md for system rules, stock data format, DB schema, and architecture.
> This file covers reports-specific implementation details only.

All PDF generation uses ReportLab. PDFs save to Desktop (`C:\Users\Josh\Desktop\`) because Python cannot write to Documents/ — see root CLAUDE.md Section 15.

---

## reports/pdf_generator.py (facade)
Function: `generate_report(portfolio_type, ranked_stocks, output_path, total_stocks_screened)`
Shows all qualifying stocks (those passing the dynamic threshold). Includes sentiment panel when data is present.

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
