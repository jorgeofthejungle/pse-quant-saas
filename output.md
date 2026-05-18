# StockPilot PH – Redesign & Scoring Engine Fixes

## Problem Statement

The operator and paying Discord members interact with StockPilot PH through two primary surfaces: the PDF report (delivered via Discord) and the operator dashboard (Flask). Both surfaces were built for function over form — the PDF uses Helvetica and ReportLab defaults, producing a utilitarian report that does not reflect the quality of the underlying analysis. The dashboard uses hand-rolled CSS with no consistent design system, making it visually inconsistent and harder to scan at a glance.

Separately, the scoring engine contains several math decisions that were reasonable at v1 but have known gaps: the momentum bonus is too small to meaningfully differentiate accelerating companies, the EPS stability sub-score penalises improving loss-makers unfairly, the intrinsic value blend does not vary by portfolio type, and the direction sub-score in the persistence layer gives no credit for partial improvement.

## Solution

### Workstream A — PDF Redesign (parallel with B)

Redesign the StockPilot PH PDF report using a premium fintech SaaS aesthetic:
- Embed the Inter font (via ReportLab’s TTF embedding) for all body and heading text.
- Redesign the cover page as a unified brand moment: navy background, gold accent line, company logo, report date, and a clean subtitle “Market Intelligence Report”.
- Slim down the rankings table to only the most scannable columns: Ticker, Company Name, Score (out of 100), Margin of Safety, and one-line broker consensus.
- Restrict stock detail pages to the top 10 per portfolio (Growth, Value, Income, Micro-Cap) and show Score + MoS as the hero elements, followed by a compact 3×3 metric grid (P/E, ROE, EPS growth, debt/equity, dividend yield, etc.) and a short narrative summary.
- Add a final appendix with glossary and methodology notes.

### Workstream B — Dashboard Redesign (parallel with A)

Replace hand-rolled CSS with Tailwind CSS (via CDN, no build step):
- Apply the StockPilot brand: navy sidebar, gold accents, white content area, consistent spacing and typography.
- Make the pipeline control screen the hero screen: clear status indicators (Pending, Running, Completed, Failed) with colour-coded badges, one‑click “Run Pipeline” and “Cancel” buttons, and a live log panel.
- Reorganise navigation: Pipeline → Reports → Scoring Engine → Settings, all accessible from a collapsible sidebar.
- Convert all data tables to responsive designs with sortable columns and inline action menus.

### Workstream C — Scoring Engine Math Fixes (after A and B are stable)

Apply six targeted fixes to the scoring engine:

1. **Widen the momentum bonus**: Increase the maximum momentum contribution from 5 points to 12 points, with a steeper gradient for quarterly price acceleration.
2. **Fix the shrinking-loss EPS floor**: For companies with negative EPS but improving year-over-year (loss shrinking), set the EPS stability sub-score base to 40 (instead of 0) to avoid unfair penalisation.
3. **Split intrinsic value blends by portfolio type**:  
   - Growth: 70% DCF + 30% PEG ratio  
   - Value: 60% Graham number + 40% DCF  
   - Income: 50% DCF + 50% dividend discount model  
   - Micro‑Cap: 50% asset-based + 50% DCF (with revenue multiples as tiebreaker)
4. **Tighten the 2‑year data confidence multiplier**: Reduce the confidence penalty for companies with only 2 years of data from 15% to 8%, and apply a smooth linear interpolation for data lengths between 2 and 5 years.
5. **Award partial credit on the persistence direction sub-score**: Instead of binary (0 or 100), award points proportional to the improvement:  
   - 30% credit if direction metric improved year‑over‑year but is still negative  
   - 70% credit if improvement crosses zero into positive territory  
   - 100% credit if it remains positive and growing
6. **Normalise industry‑relative scores**: Ensure all sub-scores are scaled relative to industry peers before blending, to avoid sector biases in the final composite.

## User Stories

1. **As a paying Discord member**, I want to receive a professional-looking PDF report so that I can share it with colleagues without embarrassment.
2. **As a paying Discord member**, I want to see only the most critical data (score and margin of safety) for each stock so that I can make decisions quickly.
3. **As a paying Discord member**, I want the top‑10 per portfolio to be highlighted with detailed metrics, so that I can focus on the strongest candidates.
4. **As the operator**, I want a dashboard that is visually consistent and easy to navigate, so that I can manage pipelines without frustration.
5. **As the operator**, I want to see the real‑time status of each pipeline run with clear actionable controls, so that I can intervene immediately when something fails.
6. **As a paying Discord member**, I want the scoring engine to more fairly rank companies that are turning around (losses narrowing), so that improving businesses are not unfairly penalised.
7. **As a paying Discord member**, I want momentum to be a bigger factor in the score, so that stocks with recent positive price action get appropriate attention.
8. **As a paying Discord member**, I want the intrinsic value estimate to be tailored to the portfolio style (growth vs value vs income vs micro‑cap), so that the score reflects the right valuation framework.
9. **As the operator**, I want the confidence multiplier to be less harsh on newer companies (2 years of data) so that promising small‑caps are not automatically downgraded.
10. **As a paying Discord member**, I want the persistence direction sub-score to recognise partial recovery, so that stocks that are improving but not yet fully recovered get a fair score.

## Success Criteria

- PDF report receives positive feedback from at least 3 paying members in a blind A/B test.
- Dashboard load time (pipeline status screen) under 2 seconds on a typical operator connection.
- All six scoring engine fixes pass unit tests and do not change the relative order of the top 20% of stocks by more than two positions.
- Tailwind CSS integration does not break any existing JavaScript functionality (form submissions, filters, modals).

## Timeline and Dependencies

- **Week 1–2**: Workstream A (PDF) and Workstream B (Dashboard) in parallel.  
  *Dependency*: PDF requires a new ReportLab font registration script; dashboard requires switching CSS framework without breaking Flask templates.
- **Week 3**: Workstream C (Scoring engine) after A and B are stable.  
  *Dependency*: Must have a staging environment with the updated scoring engine to compare outputs.
- **Week 4**: Integration testing, UAT with operator, and release.

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Font embedding may break on some server environments | Test on the production server early; provide fallback to Helvetica if embedding fails |
| Tailwind CDN may increase page load time | Use a minified CDN (from unpkg) and implement lazy loading for non-critical components |
| Scoring engine changes could shift rankings unexpectedly | Run full historical backtest on at least 6 months of data; compare decile distributions |
| Operator may resist dashboard changes | Schedule a demo early; gather feedback and iterate before final deployment |