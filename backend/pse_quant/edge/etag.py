"""
pse_quant/edge/etag.py — Cryptographic Entity Tag (ETag) Computation & Validation
PSE Quant SaaS — Lab 18
"""

from __future__ import annotations
import hashlib
from typing import Optional


def compute_etag(content: bytes) -> str:
    """
    Computes a deterministic strong ETag from response content bytes using SHA-256.
    Returns quoted RFC 7232 format: '"<16-char-hex>"'
    """
    digest = hashlib.sha256(content).hexdigest()[:16]
    return f'"{digest}"'


def is_etag_match(client_if_none_match: Optional[str], computed_etag: str) -> bool:
    """
    Evaluates whether the client's If-None-Match header matches the computed ETag.
    Handles weak ETags (W/ prefix), quotes, and comma-separated lists of tags.
    """
    if not client_if_none_match:
        return False

    raw_computed = computed_etag.strip('"')
    tokens = [t.strip() for t in client_if_none_match.split(",")]

    for token in tokens:
        if token == "*":
            return True
        # Strip weak validator prefix if present (W/"...")
        cleaned = token.lstrip("W/").strip('"')
        if cleaned == raw_computed:
            return True

    return False
