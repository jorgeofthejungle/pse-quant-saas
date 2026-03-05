# ============================================================
# news_fetcher.py — PSE Stock News Headline Fetcher
# PSE Quant SaaS — Phase 3 Sentiment
# ============================================================
# Fetches recent news headlines for a PSE ticker from:
#   1. Yahoo Finance RSS  (ticker.PS format)
#   2. BusinessWorld RSS
#   3. Inquirer Business RSS
#
# Returns a list of headline strings (max 10, most recent first).
# Gracefully skips any source that fails or times out.
# ============================================================

import xml.etree.ElementTree as ET
import urllib.request
import urllib.error
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

YAHOO_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}.PS&region=PH&lang=en-US"
BW_RSS    = "https://www.bworldonline.com/feed/"
INQ_RSS   = "https://business.inquirer.net/feed/"

TIMEOUT = 8  # seconds per request


def fetch_headlines(ticker: str, company_name: str, max_results: int = 10) -> list[str]:
    """
    Fetches and deduplicates headlines from all RSS sources.
    Filters to articles mentioning the ticker or first word of company_name.
    Returns list of headline strings, most recent first (up to max_results).
    """
    all_items: list[tuple[str, datetime | None]] = []

    # Source 1: Yahoo Finance (ticker-specific — most reliable)
    url = YAHOO_RSS.format(ticker=ticker)
    xml = _fetch_url(url)
    if xml:
        all_items.extend(_parse_rss(xml))

    # Sources 2 & 3: General PH business news (filter by relevance)
    for rss_url in (BW_RSS, INQ_RSS):
        xml = _fetch_url(rss_url)
        if xml:
            for title, pub_date in _parse_rss(xml):
                if _is_relevant(title, ticker, company_name):
                    all_items.append((title, pub_date))

    # Sort by date descending (None dates go to end)
    all_items.sort(key=lambda x: x[1] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    # Deduplicate by title and cap at max_results
    seen: set[str] = set()
    results: list[str] = []
    for title, _ in all_items:
        t = title.strip()
        if t and t not in seen:
            seen.add(t)
            results.append(t)
        if len(results) >= max_results:
            break

    return results


def _fetch_url(url: str) -> str | None:
    """Fetches URL content, returns text or None on any error."""
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 PSE-Quant-Bot/1.0'}
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except Exception:
        return None


def _parse_rss(xml_text: str) -> list[tuple[str, datetime | None]]:
    """
    Parses RSS XML and returns list of (title, pub_date) tuples.
    pub_date is timezone-aware datetime or None if unparseable.
    """
    items: list[tuple[str, datetime | None]] = []
    try:
        root = ET.fromstring(xml_text)
        # Handle both RSS 2.0 and Atom namespaces
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        channel = root.find('channel')
        entries = channel.findall('item') if channel is not None else []
        if not entries:
            entries = root.findall('.//item')

        for item in entries:
            title_el = item.find('title')
            date_el  = item.find('pubDate')
            title = title_el.text.strip() if title_el is not None and title_el.text else ''
            if not title:
                continue
            pub_date = None
            if date_el is not None and date_el.text:
                try:
                    pub_date = parsedate_to_datetime(date_el.text.strip())
                except Exception:
                    pass
            items.append((title, pub_date))
    except ET.ParseError:
        pass
    return items


def _is_relevant(title: str, ticker: str, company_name: str) -> bool:
    """
    Returns True if headline mentions the ticker or the first word
    of the company name (case-insensitive).
    """
    title_lower = title.lower()
    if ticker.lower() in title_lower:
        return True
    first_word = company_name.split()[0].lower() if company_name else ''
    if len(first_word) >= 4 and first_word in title_lower:
        return True
    return False


# ── CLI test ─────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse
    import sys

    parser = argparse.ArgumentParser(description='Fetch PSE stock headlines')
    parser.add_argument('--ticker',  required=True, help='PSE ticker, e.g. DMC')
    parser.add_argument('--name',    default='',    help='Company name (optional)')
    parser.add_argument('--max',     type=int, default=10)
    args = parser.parse_args()

    print(f"Fetching headlines for {args.ticker}...")
    headlines = fetch_headlines(args.ticker, args.name, args.max)
    if not headlines:
        print("No headlines found.")
        sys.exit(0)

    print(f"Found {len(headlines)} headline(s):")
    for i, h in enumerate(headlines, 1):
        print(f"  {i}. {h}")
