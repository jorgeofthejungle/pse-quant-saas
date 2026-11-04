# ============================================================
# sentiment_engine.py — News Sentiment Analyser
# PSE Quant SaaS — Phase 3 Sentiment
# ============================================================
# Uses Claude Haiku to classify news sentiment for PSE stocks.
# Reads ANTHROPIC_API_KEY from .env.
# Falls back gracefully if key is missing or API fails.
#
# Sentiment is INFORMATIONAL ONLY — it does not change scores.
# ============================================================

import json
import os
from datetime import date, datetime

# Lazy import: won't crash if anthropic isn't installed
try:
    import anthropic as _anthropic_module
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

try:
    from config import PIPELINE_AI_MODEL as MODEL
except ImportError:
    MODEL = "claude-haiku-4-5-20251001"

_PROMPT_TEMPLATE = """\
You are a financial news analyst for the Philippine Stock Exchange.
Analyze the following headlines for {ticker} ({company_name}, sector: {sector}).

Your role is to classify tone — not to advise on investing.
Be neutral, factual, and concise.

Headlines:
{headlines_text}

Return ONLY valid JSON (no explanation, no markdown) with exactly these fields:
{{
  "score": <float from -1.0 (very negative) to 1.0 (very positive)>,
  "category": "<Positive|Neutral|Negative>",
  "key_events": ["<short phrase>", ...],
  "summary": "<1-2 sentences, plain English, neutral tone>",
  "opportunistic_flag": <0 or 1>,
  "risk_flag": <0 or 1>
}}

Rules:
- key_events: up to 3 specific events mentioned in the headlines
- summary: mention the company name; do not use "buy", "sell", or any investment advice
- opportunistic_flag=1 only if headlines mention a clear near-term positive catalyst
  (e.g. earnings beat, dividend increase, major contract win, rights issue approval)
- risk_flag=1 only if headlines mention material downside (e.g. regulatory action,
  credit downgrade, major litigation, profit warning, CEO departure under negative circumstances)
"""


def analyze_sentiment(ticker: str, company_name: str, sector: str,
                      headlines: list[str]) -> dict | None:
    """
    Calls Claude Haiku to analyse sentiment of headline list.
    Caches result in DB for today (UNIQUE(ticker, date)).
    Returns structured dict or None on any failure.

    Return dict keys: score, category, key_events, summary,
                      opportunistic_flag, risk_flag, headlines, last_updated
    """
    if not headlines:
        return None

    api_key = os.environ.get('ANTHROPIC_API_KEY') or _load_dotenv_key()
    if not api_key:
        return None
    if not _ANTHROPIC_AVAILABLE:
        return None

    headlines_text = '\n'.join(f'{i+1}. {h}' for i, h in enumerate(headlines))
    prompt = _PROMPT_TEMPLATE.format(
        ticker=ticker,
        company_name=company_name,
        sector=sector or 'General',
        headlines_text=headlines_text,
    )

    try:
        client = _anthropic_module.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=MODEL,
            max_tokens=512,
            messages=[{'role': 'user', 'content': prompt}],
        )
        raw = response.content[0].text.strip()
        data = json.loads(raw)
    except Exception as e:
        print(f"  [sentiment] API error for {ticker}: {e}")
        return None

    # Normalise and attach metadata
    result = {
        'score':              float(data.get('score', 0.0)),
        'category':           str(data.get('category', 'Neutral')),
        'key_events':         list(data.get('key_events') or [])[:3],
        'summary':            str(data.get('summary', '')),
        'opportunistic_flag': int(bool(data.get('opportunistic_flag', 0))),
        'risk_flag':          int(bool(data.get('risk_flag', 0))),
        'headlines':          headlines,
        'last_updated':       date.today().isoformat(),
    }

    # Cache in DB
    try:
        from db.database import upsert_sentiment
        upsert_sentiment(ticker, result['last_updated'], result)
    except Exception as e:
        print(f"  [sentiment] DB cache error for {ticker}: {e}")

    return result


def enrich_with_sentiment(stocks: list[dict]) -> None:
    """
    Enriches each stock dict in-place with a 'sentiment_data' key.
    Checks DB cache first (today's date); fetches live only on cache miss.
    Silently skips if API key is missing or any step fails.
    """
    today = date.today().isoformat()

    try:
        from db.database import get_sentiment, init_db
        from scraper.news_fetcher import fetch_headlines
    except Exception as e:
        print(f"  [sentiment] import error: {e}")
        for s in stocks:
            s['sentiment_data'] = None
        return

    for stock in stocks:
        ticker = stock.get('ticker', '')
        stock['sentiment_data'] = None
        try:
            # Check 24-hour cache
            cached = get_sentiment(ticker)
            if cached and cached.get('date') == today:
                stock['sentiment_data'] = cached
                continue

            # Fetch live headlines
            headlines = fetch_headlines(ticker, stock.get('name', ''))
            if not headlines:
                continue

            # Analyse with Claude Haiku
            result = analyze_sentiment(
                ticker,
                stock.get('name', ticker),
                stock.get('sector', ''),
                headlines,
            )
            stock['sentiment_data'] = result

        except Exception as e:
            print(f"  [sentiment] error for {ticker}: {e}")


def classify_signal(
    sentiment_data: dict,
    mos_pct: float | None,
    overall_score: float,
) -> dict:
    """
    Deterministic signal classification using sentiment + fundamentals.
    Rules evaluated top-to-bottom; first match wins.

    Parameters:
        sentiment_data  — dict returned by analyze_sentiment()
                          Keys used: score, opportunistic_flag, risk_flag
        mos_pct         — Margin of Safety % (None if intrinsic value unavailable)
        overall_score   — Portfolio score 0-100 from scorer.py

    Returns:
        {
          'signal':    'potential_opportunity' | 'half_position' | 'caution' | 'monitor',
          'label':     Human-readable label string,
          'reasoning': One-line explanation built from inputs,
          'level':     'positive' | 'neutral' | 'negative',
        }
    """
    score    = float(sentiment_data.get('score', 0.0))
    opp_flag = int(bool(sentiment_data.get('opportunistic_flag', 0)))
    risk_flag = int(bool(sentiment_data.get('risk_flag', 0)))
    mos       = mos_pct if mos_pct is not None else -1.0

    # ── Rule 1: Potential Opportunity ────────────────────────
    if (
        (opp_flag == 1 and score >= 0.3 and mos >= 20)
        or (score >= 0.5 and mos >= 30 and overall_score >= 65)
    ):
        mos_str = f'{mos:.0f}% margin of safety' if mos_pct is not None else 'no MoS data'
        return {
            'signal':    'potential_opportunity',
            'label':     'Potential Opportunity',
            'reasoning': (
                f'Positive news catalyst + {mos_str} + score {overall_score:.0f}/100'
            ),
            'level': 'positive',
        }

    # ── Rule 2: Half Position Signal ─────────────────────────
    if (
        (opp_flag == 1 and score >= 0.2 and (mos_pct is None or mos < 20))
        or (score >= 0.3 and mos >= 10 and overall_score >= 50)
    ):
        mos_str = f'{mos:.0f}% margin of safety' if mos_pct is not None else 'no MoS data'
        return {
            'signal':    'half_position',
            'label':     'Half Position Signal',
            'reasoning': (
                f'Positive sentiment but limited margin of safety '
                f'({mos_str}, score {overall_score:.0f}/100)'
            ),
            'level': 'positive',
        }

    # ── Rule 3: Caution Signal ───────────────────────────────
    if (risk_flag == 1 and score <= -0.3) or (score <= -0.5):
        return {
            'signal':    'caution',
            'label':     'Caution Signal',
            'reasoning': (
                f'Negative news sentiment (score {score:.2f}) '
                + ('with material risk flag' if risk_flag else '')
            ).strip(),
            'level': 'negative',
        }

    # ── Rule 4: Monitor (default) ────────────────────────────
    return {
        'signal':    'monitor',
        'label':     'Monitor',
        'reasoning': f'Sentiment neutral or insufficient signal (score {score:.2f})',
        'level':     'neutral',
    }


def _load_dotenv_key() -> str | None:
    """Try to load ANTHROPIC_API_KEY from .env without requiring dotenv."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
        return os.environ.get('ANTHROPIC_API_KEY')
    except ImportError:
        # Manual parse of .env
        env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        try:
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('ANTHROPIC_API_KEY='):
                        return line.split('=', 1)[1].strip().strip('"\'')
        except FileNotFoundError:
            pass
    return None


# ── CLI test ─────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse, sys
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description='Test sentiment analysis for a PSE ticker')
    parser.add_argument('--ticker', required=True, help='PSE ticker, e.g. DMC')
    parser.add_argument('--name',   default='',    help='Company name (optional)')
    parser.add_argument('--sector', default='',    help='Sector (optional)')
    args = parser.parse_args()

    print(f"Fetching headlines for {args.ticker}...")
    from scraper.news_fetcher import fetch_headlines
    headlines = fetch_headlines(args.ticker, args.name)
    if not headlines:
        print("No headlines found — cannot run sentiment analysis.")
        sys.exit(0)

    print(f"Found {len(headlines)} headline(s). Analysing...")
    result = analyze_sentiment(args.ticker, args.name or args.ticker, args.sector, headlines)
    if not result:
        print("Sentiment analysis failed (check ANTHROPIC_API_KEY in .env).")
        sys.exit(1)

    print(f"\nSentiment for {args.ticker}:")
    print(f"  Category : {result['category']}")
    print(f"  Score    : {result['score']:.2f}")
    print(f"  Summary  : {result['summary']}")
    print(f"  Events   : {', '.join(result['key_events'])}")
    print(f"  Opp flag : {'YES' if result['opportunistic_flag'] else 'no'}")
    print(f"  Risk flag: {'YES' if result['risk_flag'] else 'no'}")
