# ============================================================
# security.py — Rate Limiting & Input Sanitization
# PSE Quant SaaS — Dashboard
# ============================================================
# Lightweight in-memory rate limiter (no Redis required).
# Suitable for a localhost single-admin tool.
# ============================================================

import re
import time
import threading
from collections import defaultdict
from functools import wraps
from flask import request, jsonify


# ── In-memory rate limiter ────────────────────────────────────

_counters: dict = defaultdict(list)   # {key: [timestamps...]}
_lock = threading.Lock()


def _check_rate(key: str, limit: int, window_secs: int = 60) -> bool:
    """
    Returns True if the key is within the allowed rate.
    Removes timestamps older than window_secs on each call.
    """
    now = time.time()
    with _lock:
        timestamps = _counters[key]
        # Evict timestamps outside the window
        _counters[key] = [t for t in timestamps if now - t < window_secs]
        if len(_counters[key]) >= limit:
            return False
        _counters[key].append(now)
        return True


def rate_limit(limit: int = 60, window_secs: int = 60, per: str = 'ip'):
    """
    Decorator factory. Applies per-IP rate limiting to a Flask route.

    Usage:
        @stocks_bp.route('/api/stocks/search')
        @rate_limit(limit=60)
        def api_search(): ...
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = f"{fn.__name__}:{request.remote_addr}"
            if not _check_rate(key, limit, window_secs):
                return jsonify({'error': 'Rate limit exceeded. Please wait a moment.'}), 429
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ── Input sanitization helpers ────────────────────────────────

_TICKER_RE = re.compile(r'^[A-Z0-9]{1,10}$')


def sanitize_ticker(raw: str) -> str | None:
    """
    Returns the sanitized ticker (uppercase, alphanumeric, max 10 chars).
    Returns None if the input is invalid.
    """
    if not raw:
        return None
    clean = raw.strip().upper()[:10]
    return clean if _TICKER_RE.match(clean) else None


def sanitize_text(raw: str, max_len: int = 255) -> str:
    """Returns a stripped, length-limited string. Never returns None."""
    if not raw:
        return ''
    return str(raw).strip()[:max_len]
