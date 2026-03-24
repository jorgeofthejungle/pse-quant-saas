# engine/CLAUDE.md — Scoring Engine Implementation Details
> See root CLAUDE.md for system rules, stock data format, DB schema, and architecture.
> This file covers engine-specific implementation details only.

All engine modules are pure Python — no AI calls except `sentiment_engine.py` which uses `PIPELINE_AI_MODEL` from `config.py`. Scoring weights live in `config.py SCORER_WEIGHTS`. Sector sub-score weights live in `config.py SECTOR_SCORING_CONFIG`. Do not modify scoring logic without reading `scorer_v2.py` first.

---

## engine/metrics.py
Calculates: `pe, pb, roe, de, dividend_yield, payout_ratio, fcf, fcf_yield, fcf_coverage, cagr, ev_ebitda`
All functions return `float | None`. Never raise on bad input.

## engine/filters_v2.py
Function: `filter_unified(stock)` → returns `(eligible: bool, reason: str)`
Hard filters: min 2 years of EPS/Revenue data, normalized EPS > 0,
no persistent negative OCF (2+ consecutive years), D/E ≤ 3.0x (non-financial) or ≤ 10x (bank) or ≤ 4.0x (REIT).
*(Phase 13: Relaxed from 3-year to 2-year minimum. Confidence multiplier handles the penalty.)*

## engine/sector_groups.py
Function: `get_scoring_group(stock)` → returns group string: `'bank' | 'reit' | 'holding' | 'property' | 'industrial' | 'mining' | 'services'`
Priority: is_bank/BANK_TICKERS → is_reit/REIT_WHITELIST → sector string → `'services'` (fallback).
Function: `get_layer_config(group, layer)` → returns sub-score weight dict from `SECTOR_SCORING_CONFIG`.
Function: `describe_group(stock)` → human-readable label for PDF/debug.

## engine/scorer_v2.py (unified 3-layer scorer)
Function: `score_unified(stock, financials_history=None, portfolio_type='unified')` → returns `(score: float, breakdown: dict)`
Resolves `scoring_group` internally via `get_scoring_group(stock)`.
Three layers: health, improvement, persistence — weights from `config.py SCORER_WEIGHTS`.
Dynamic threshold applied in `rank_stocks_v2()`: mean + 0.5 SD of scored universe; hard floor at 45.
Applies data confidence multiplier to final score.
**Weights and thresholds are configured in `config.py`. Do not change without explicit instruction.**

## engine/scorer_health.py
Function: `score_health(stock, scoring_group, sector_medians=None)` → `(float|None, dict)`
Config-driven via `get_layer_config(scoring_group, 'health')`.
Sub-scores: `roe`, `ni_margin`, `de_ratio`, `eps_stability`, `pb`, `dividend_yield`, `fcf_yield`.
D/E excluded for banks (`_score_de_ratio` returns None for bank group).
NI Margin = net_income / revenue — available for 246/255 stocks; capped at 15-20% weight.
Thresholds calibrated by `engine/calibrate_thresholds.py`, stored in `settings` DB table with `config.py` fallbacks.

## engine/scorer_improvement.py
Function: `score_improvement(stock, financials_history, scoring_group)` → `(float|None, dict)`
Config-driven via `get_layer_config(scoring_group, 'improvement')`.
Sub-scores: `revenue_delta`, `eps_delta`, `roe_delta`, `dps_delta`.
Uses recency-weighted smoothed deltas (50/30/20 newest-first).
Momentum bonus: ±5pt adjustment for stocks with 5yr+ data based on recent vs prior growth.

## engine/scorer_persistence.py
Function: `score_persistence(stock, scoring_group)` → `(float|None, dict)`
Config-driven via `get_layer_config(scoring_group, 'persistence')`.
Sub-scores: `revenue`, `eps`, `dps`, `direction`.
Blended formula per metric: direction (60pts) + magnitude (20pts) + streak bonus (20pts).
DPS persistence for REITs filters zero/None years before scoring.

## engine/scorer_utils.py
`_blend(scores_weights)` → `float | None` — returns None (not 0.0) when all sub-scores are None. This is critical: returning 0.0 would create a fake penalty.
`_blend_checked(scores_weights, min_subscores=2)` → `float | None` — requires at least 2 valid sub-scores; returns None if below threshold to prevent single-metric distortion.
`normalise(value, low, high)` → score 0–100.

## engine/mos.py
Functions: `calc_ddm`, `calc_eps_pe`, `calc_dcf`, `calc_mos_price`, `calc_mos_pct`, `calc_hybrid_intrinsic`
Risk-free rate = 6.5% (PH 10Y T-bond). Max DDM growth rate capped at 7%.
Discount rate = risk-free + equity premium (5%) + size premium (0-5%) + sector premium (0-2%).
All constants imported from `config.py` — no local duplicates.

## engine/sentiment_engine.py
Uses `PIPELINE_AI_MODEL` from `config.py` (Claude Haiku).
Entry: `enrich_with_sentiment(stocks)` — enriches list in-place.
Caches results in `sentiment` DB table for 24 hours.
Returns `None` silently if `ANTHROPIC_API_KEY` is missing.
**Enrich AFTER filter+score, top 10 only** — enriching all stocks causes excessive RSS fetches.

## engine/validator.py — check_price_staleness()
- `check_price_staleness(stock)` → `{price_date, days_stale, is_stale, is_critical, warning}`
- Warn threshold: `PRICE_STALENESS_WARN_DAYS = 5` days; critical: `PRICE_STALENESS_ERROR_DAYS = 30` days
- DB fallback: queries `SELECT MAX(date) FROM prices WHERE ticker = ?` if `price_date` not in stock dict
- Integrated into `validate_stock()` return dict as `'price_staleness'` key

## engine/validator.py — hard-block thresholds
- `BLOCK_THRESHOLDS`: `'roe': ('<', -50.0, ...)` — ROE < -50% is a hard block (not warn)
- `BLOCK_THRESHOLDS`: `'pb': ('>', 50.0, ...)` — P/B > 50 is a hard block
- `MIN_COMPLETENESS = 0.40` — 40% of scored fields must be populated
