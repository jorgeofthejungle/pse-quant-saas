# ============================================================
# discord_monthly.py — Monthly Scheduled Reports
# PSE Quant SaaS
# ============================================================
# Two posts on the 1st of each month to #deep-analysis:
#   1. send_dividend_calendar()  — top dividend payers by yield
#   2. send_model_performance()  — score trends month-over-month
# ============================================================

from datetime import datetime
from discord.discord_core import _post_webhook, WEBHOOKS, DISCLAIMER


def send_dividend_calendar(
    webhook_url: str,
    month_str:   str,   # e.g. 'April 2026'
    payers:      list,  # [{ticker, name, dps, year, yield_pct}]
    recent_disc: list,  # [{ticker, date, title}] from disclosures table
) -> bool:
    """
    Posts the monthly dividend calendar to #deep-analysis (premium).
    Shows top dividend-paying stocks by yield + recent announcements.

    Parameters:
        payers      -- sorted by yield_pct DESC (pre-queried from DB)
        recent_disc -- dividend disclosures from the last 45 days
    """
    url = webhook_url or WEBHOOKS.get('deep_analysis', '')
    if not url:
        print("[discord_monthly] DISCORD_WEBHOOK_DEEP_ANALYSIS not set — skipping calendar")
        return False

    fields = []

    # ── Top dividend payers ───────────────────────────────────
    if payers:
        lines = []
        for i, p in enumerate(payers[:12], 1):
            ticker    = p.get('ticker', '?')
            dps       = p.get('dps') or 0
            yield_pct = p.get('yield_pct')
            year      = p.get('year', '')
            yield_str = f' · **{yield_pct:.1f}% yield**' if yield_pct is not None else ''
            lines.append(f'**{i}. {ticker}** — ₱{dps:.2f}/share{yield_str}  _(FY{year})_')
        fields.append({
            'name':   '💰 Top Dividend Payers (by yield)',
            'value':  '\n'.join(lines),
            'inline': False,
        })
    else:
        fields.append({
            'name':   '💰 Dividend Payers',
            'value':  'No dividend data available yet.',
            'inline': False,
        })

    # ── Recent dividend announcements (last 45 days) ──────────
    if recent_disc:
        disc_lines = []
        for d in recent_disc[:8]:
            ticker = d.get('ticker', '?')
            dt     = d.get('date', '')[:10]
            title  = (d.get('title') or '')[:80]
            disc_lines.append(f'**{ticker}** — {dt} — _{title}_')
        fields.append({
            'name':   '📢 Recent Dividend Announcements',
            'value':  '\n'.join(disc_lines),
            'inline': False,
        })

    fields.append({
        'name':   '📌 Note',
        'value':  (
            'DPS and yields are from the latest annual financial filings. '
            'Actual dividend declarations vary — always check PSE Edge for official ex-dates and record dates.'
        ),
        'inline': False,
    })

    embed = {
        'title':       f'📅 Dividend Calendar — {month_str}',
        'description': (
            'Monthly overview of dividend-paying stocks in our ranked PSE universe. '
            'Sorted by dividend yield using the most recent available financial data.'
        ),
        'color':   0x27AE60,
        'fields':  fields,
        'footer':  {'text': DISCLAIMER},
        'timestamp': datetime.utcnow().isoformat() + 'Z',
    }
    return _post_webhook(url, {'embeds': [embed]})


def send_model_performance(
    webhook_url:  str,
    month_str:    str,         # e.g. 'April 2026'
    current:      list,        # [{ticker, name, score, rank, category}] top 20
    prior:        dict,        # {ticker: {score, rank}} from ~30 days ago
    latest_date:  str,
    prior_date:   str | None,
) -> bool:
    """
    Posts the monthly model performance snapshot to #deep-analysis.
    Compares current unified scores vs ~30 days ago.

    Parameters:
        current     -- sorted by rank ASC, top 20 from latest run
        prior       -- dict keyed by ticker from prior run (~30 days ago)
        latest_date -- ISO date of the current run
        prior_date  -- ISO date of the prior run (None if no prior data)
    """
    url = webhook_url or WEBHOOKS.get('deep_analysis', '')
    if not url:
        print("[discord_monthly] DISCORD_WEBHOOK_DEEP_ANALYSIS not set — skipping performance")
        return False

    def _grade(score: float) -> str:
        if score >= 80: return 'A'
        if score >= 65: return 'B'
        if score >= 50: return 'C'
        if score >= 35: return 'D'
        return 'F'

    fields = []

    # ── Current top 10 with MoM delta ────────────────────────
    if current:
        lines = []
        for s in current[:10]:
            ticker     = s.get('ticker', '?')
            score      = s.get('score') or 0
            rank       = s.get('rank', '?')
            grade      = _grade(score)
            prior_data = prior.get(ticker, {})
            prior_score = prior_data.get('score')
            prior_rank  = prior_data.get('rank')

            delta_str = ''
            if prior_score is not None:
                delta     = score - prior_score
                delta_str = f'  _{delta:+.1f} pts_'

            arrow = ''
            if prior_rank is not None and isinstance(rank, int):
                if rank < prior_rank:
                    arrow = ' ▲'
                elif rank > prior_rank:
                    arrow = ' ▼'

            lines.append(
                f'**#{rank}{arrow} {ticker}** — {score:.1f} Grade {grade}{delta_str}'
            )
        fields.append({
            'name':   f'🏆 Current Top 10  ({latest_date})',
            'value':  '\n'.join(lines),
            'inline': False,
        })

    # ── Biggest movers (top 20 scope) ─────────────────────────
    if prior:
        movers = []
        for s in current[:20]:
            ticker = s.get('ticker', '?')
            score  = s.get('score') or 0
            p      = prior.get(ticker, {})
            if p.get('score') is not None:
                delta = score - p['score']
                if abs(delta) >= 2.0:
                    movers.append((ticker, delta, score))
        movers.sort(key=lambda x: abs(x[1]), reverse=True)

        if movers:
            mover_lines = []
            for ticker, delta, score in movers[:6]:
                sign = '▲' if delta > 0 else '▼'
                mover_lines.append(f'{sign} **{ticker}**  {delta:+.1f} pts → {score:.1f}/100')
            fields.append({
                'name':   '📈 Biggest Movers (month-over-month)',
                'value':  '\n'.join(mover_lines),
                'inline': False,
            })

    # ── Top 10 composition changes ────────────────────────────
    if prior:
        current_top10 = {s.get('ticker') for s in current[:10]}
        prior_top10   = {t for t, p in prior.items() if (p.get('rank') or 999) <= 10}
        new_in  = current_top10 - prior_top10
        dropped = prior_top10 - current_top10

        changes = []
        if new_in:
            changes.append('**Entered top 10:** ' + ', '.join(sorted(new_in)))
        if dropped:
            changes.append('**Dropped from top 10:** ' + ', '.join(sorted(dropped)))
        if not changes:
            changes.append('Top 10 composition unchanged from last month.')
        fields.append({
            'name':   '🔄 Top 10 Changes',
            'value':  '\n'.join(changes),
            'inline': False,
        })

    # ── Context ───────────────────────────────────────────────
    prior_label = f'vs {prior_date}' if prior_date else '(no prior data for comparison)'
    fields.append({
        'name':   '📊 How to Read This',
        'value':  (
            f'Scores compared: **{latest_date}** {prior_label}.\n'
            'Scoring uses a 4-layer framework: Health (25%) · Improvement (30%) · '
            'Acceleration (15%) · Persistence (30%).\n\n'
            '_Score shifts reflect changes in financial data, not market prices. '
            'A rising score means the company\'s fundamentals are improving._'
        ),
        'inline': False,
    })

    embed = {
        'title':       f'📊 Model Performance — {month_str}',
        'description': (
            'Month-over-month comparison of StockPilot PH unified scores across all 223 PSE stocks. '
            'Scores update daily at 4 PM PHT — this snapshot captures the full month\'s shift.'
        ),
        'color':   0x2980B9,
        'fields':  fields,
        'footer':  {
            'text': (
                'StockPilot PH · Scores are mathematical rankings, not investment advice. '
                'Data sourced from PSE Edge.'
            )
        },
        'timestamp': datetime.utcnow().isoformat() + 'Z',
    }
    return _post_webhook(url, {'embeds': [embed]})
