"""
pse_quant/scraper/client.py — Resilient HTTP Client for PSE Edge
Provides session warm-up, polite rate-limiting, Full Jitter backoff,
and Circuit Breaker fast-fail protection against upstream outages.
"""

from __future__ import annotations
import time
import logging
import requests
from typing import Any, Optional

from pse_quant.scraper.resilience import (
    CircuitBreaker,
    global_pse_edge_circuit,
    calculate_jittered_backoff,
)

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
    """Wrapper around requests.Session configured with Circuit Breaker and Jittered Retries."""

    def __init__(
        self,
        delay_secs: float = DEFAULT_DELAY_SECS,
        circuit: Optional[CircuitBreaker] = None,
    ):
        self.delay_secs = delay_secs
        self.circuit = circuit or global_pse_edge_circuit
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._warmed_up = False

    def warm_up(self) -> bool:
        """Initializes cookies by requesting the PSE Edge homepage."""
        if not self.circuit.can_execute():
            logger.warning(f"Skipping warm_up: CircuitBreaker [{self.circuit.name}] is OPEN.")
            return False

        try:
            resp = self.session.get(PSE_EDGE_BASE_URL, timeout=DEFAULT_TIMEOUT_SECS)
            self._warmed_up = resp.status_code == 200
            if self._warmed_up:
                self.circuit.record_success()
            return self._warmed_up
        except Exception as e:
            logger.warning(f"Failed to warm up PSE Edge session: {e}")
            self.circuit.record_failure(str(e))
            return False

    def get(
        self,
        endpoint_or_url: str,
        params: dict[str, Any] | None = None,
        retries: int = MAX_RETRIES,
    ) -> requests.Response | None:
        """
        Executes GET request with:
          1. Circuit breaker fast-fail (<1ms if upstream is currently down).
          2. Full Jitter exponential backoff on retries.
          3. Automatic circuit state transitions.
        """
        url = endpoint_or_url if endpoint_or_url.startswith("http") else f"{PSE_EDGE_BASE_URL}{endpoint_or_url}"

        # 1. Circuit Breaker Check
        if not self.circuit.can_execute():
            c_info = self.circuit.get_state()
            logger.error(
                f"CircuitBreaker [{self.circuit.name}] is OPEN. Fast-failing GET {url} "
                f"({c_info['cooldown_remaining_sec']}s cooldown remaining)."
            )
            return None

        if not self._warmed_up:
            self.warm_up()

        # 2. Resilient Retry Loop with Full Jitter
        for attempt in range(1, retries + 1):
            # Re-check circuit between retries
            if not self.circuit.can_execute():
                logger.error(f"CircuitBreaker tripped OPEN during retries. Aborting GET {url}")
                return None

            try:
                time.sleep(self.delay_secs)
                resp = self.session.get(url, params=params, timeout=DEFAULT_TIMEOUT_SECS)

                if resp.status_code == 200:
                    self.circuit.record_success()
                    return resp

                if resp.status_code == 429:
                    logger.warning(f"Rate limited (HTTP 429) on {url}. Applying jittered backoff...")
                    time.sleep(calculate_jittered_backoff(attempt=attempt, base_delay=self.delay_secs * 2))

                elif resp.status_code >= 500:
                    # Server errors trip the circuit breaker
                    self.circuit.record_failure(f"HTTP {resp.status_code}")
                    logger.warning(f"Upstream server error HTTP {resp.status_code} from {url} (attempt {attempt}/{retries})")
                else:
                    logger.warning(f"HTTP {resp.status_code} from {url} (attempt {attempt}/{retries})")

            except requests.RequestException as e:
                self.circuit.record_failure(str(e))
                logger.warning(f"Request error for {url}: {e} (attempt {attempt}/{retries})")

            if attempt < retries:
                backoff = calculate_jittered_backoff(attempt=attempt - 1, base_delay=self.delay_secs)
                time.sleep(backoff)

        logger.error(f"All {retries} request attempts failed for {url}")
        return None
