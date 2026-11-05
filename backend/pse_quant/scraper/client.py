"""
pse_quant/scraper/client.py — Resilient HTTP Client for PSE Edge
Provides session warm-up, rate-limiting, and exponential backoff retry handling.
"""

from __future__ import annotations
import time
import logging
import requests
from typing import Any

logger = logging.getLogger("pse_quant.scraper")

PSE_EDGE_BASE_URL = "https://edge.pse.com.ph"
DEFAULT_DELAY_SECS = 2.0
DEFAULT_TIMEOUT_SECS = 30
MAX_RETRIES = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Referer": PSE_EDGE_BASE_URL,
}


class PseEdgeClient:
    """Wrapper around requests.Session configured for PSE Edge."""

    def __init__(self, delay_secs: float = DEFAULT_DELAY_SECS):
        self.delay_secs = delay_secs
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._warmed_up = False

    def warm_up(self) -> bool:
        """Initializes cookies by requesting the PSE Edge homepage."""
        try:
            resp = self.session.get(PSE_EDGE_BASE_URL, timeout=DEFAULT_TIMEOUT_SECS)
            self._warmed_up = resp.status_code == 200
            return self._warmed_up
        except Exception as e:
            logger.warning(f"Failed to warm up PSE Edge session: {e}")
            return False

    def get(
        self,
        endpoint_or_url: str,
        params: dict[str, Any] | None = None,
        retries: int = MAX_RETRIES,
    ) -> requests.Response | None:
        """Executes GET request with polite rate-limiting and exponential backoff."""
        if not self._warmed_up:
            self.warm_up()

        url = endpoint_or_url if endpoint_or_url.startswith("http") else f"{PSE_EDGE_BASE_URL}{endpoint_or_url}"

        for attempt in range(1, retries + 1):
            try:
                time.sleep(self.delay_secs)
                resp = self.session.get(url, params=params, timeout=DEFAULT_TIMEOUT_SECS)
                if resp.status_code == 200:
                    return resp
                if resp.status_code == 429:
                    logger.warning(f"Rate limited (HTTP 429) on {url}. Applying extended backoff...")
                    time.sleep(self.delay_secs * 3)
                logger.warning(f"HTTP {resp.status_code} from {url} (attempt {attempt}/{retries})")
            except requests.RequestException as e:
                logger.warning(f"Request error for {url}: {e} (attempt {attempt}/{retries})")

            if attempt < retries:
                backoff = self.delay_secs * (2 ** (attempt - 1))
                time.sleep(backoff)

        logger.error(f"All {retries} request attempts failed for {url}")
        return None
