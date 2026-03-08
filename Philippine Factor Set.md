You are assisting in the development of quantitative stock scoring models for the Philippine Stock Exchange (PSE).

The goal is to identify undervalued companies with strong fundamentals and manageable financial risk in an emerging market environment.

The Philippine market has characteristics such as lower liquidity, family-controlled firms, retail-driven sentiment, and sensitivity to debt and interest rates. The models should reflect these realities.

FACTOR LIBRARY

Value factors:
price_to_earnings
price_to_book
free_cash_flow_yield
dividend_yield
enterprise_value_to_ebitda
margin_of_safety
earnings_yield_vs_bond_rate

Growth factors:
revenue_growth
earnings_growth
eps_growth
operating_income_growth
free_cash_flow_growth
growth_consistency

Quality factors:
return_on_equity
return_on_invested_capital
profit_margin
gross_margin_stability
asset_turnover
cash_flow_to_net_income

Balance sheet factors:
debt_ratio
debt_to_equity
interest_coverage
current_ratio
quick_ratio
financial_resilience

Liquidity factors:
average_daily_volume
volume_trend
turnover_ratio
liquidity_score

Dividend factors:
dividend_yield
dividend_growth
dividend_stability
dividend_sustainability

Market behavior factors:
momentum
relative_strength
volatility
drawdown

MODEL RULES

1. Each model must use 4 to 6 factors.
2. Each factor must have a weight.
3. Weights must sum to 1.0.
4. Risk factors should act as penalties where appropriate.
5. The model should balance value, growth, quality, and risk.
6. Avoid overly complex formulas.

OUTPUT FORMAT

Model Name

Formula:
(score formula using weighted factors)

Example format:

score =
0.30 * return_on_equity
+ 0.25 * free_cash_flow_yield
+ 0.20 * revenue_growth
+ 0.15 * dividend_yield
- 0.10 * debt_ratio

Explanation:
Explain the reasoning behind the model.

Strengths:
Describe what types of companies this model is likely to favor.

Generate 10 candidate models.