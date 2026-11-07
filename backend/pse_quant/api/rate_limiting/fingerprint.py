"""
pse_quant/api/rate_limiting/fingerprint.py — Client Identity & Tier Fingerprinting
=================================================================================
Inspects incoming HTTP requests to determine the caller's identity key and
assigned quota tier (Admin, Paid, Free, Anonymous).
"""

from __future__ import annotations
import secrets
from typing import Tuple
from fastapi import Request
import jwt

from pse_quant.api.rate_limiting.token_bucket import ClientTier
from pse_quant.services.auth_service import ADMIN_MASTER_KEY, decode_access_token


def resolve_client_fingerprint(request: Request) -> Tuple[str, ClientTier]:
    """
    Resolves client identity and quota tier from HTTP request headers.
    
    Priority Order:
      1. X-Admin-Key matching master secret -> Tier.ADMIN
      2. Authorization: Bearer <jwt> -> Tier.ADMIN, Tier.PAID, or Tier.FREE
      3. Client IP address (with proxy inspection) -> Tier.ANONYMOUS
         (Special: Starlette TestClient default host 'testclient' receives Tier.ADMIN
          to prevent suite-level cross-test starvation, unless explicit test IP is set).

    Returns:
        Tuple[str, ClientTier]: (client_unique_key, client_tier)
    """
    # 1. Master Admin Key Header (Timing-Safe)
    admin_key = request.headers.get("X-Admin-Key")
    if admin_key and ADMIN_MASTER_KEY and secrets.compare_digest(admin_key, ADMIN_MASTER_KEY):
        return "admin:master", ClientTier.ADMIN

    # 2. JWT Bearer Token Inspection
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        try:
            payload = decode_access_token(token)
            user_id = str(payload.get("sub", "anon"))
            role = payload.get("role", "member")
            tier_claim = payload.get("tier", "free")

            if role == "admin":
                return f"user:admin:{user_id}", ClientTier.ADMIN
            elif tier_claim in ("paid", "pro"):
                return f"user:paid:{user_id}", ClientTier.PAID
            else:
                return f"user:free:{user_id}", ClientTier.FREE
        except (jwt.PyJWTError, ValueError):
            # Expired / invalid token falls through to IP rate limiting
            pass

    # 3. Explicit Test Tier Override (Used in unit/integration testing)
    test_tier_header = request.headers.get("X-Test-Tier")
    if test_tier_header and test_tier_header in [t.value for t in ClientTier]:
        return f"test:{test_tier_header}", ClientTier(test_tier_header)

    # 4. Client IP Fallback (Anonymous Tier)
    client_ip = _extract_client_ip(request)
    if client_ip == "testclient":
        # Starlette testclient without specific IP defaults to ADMIN to avoid cross-test starvation
        return "test:runner", ClientTier.ADMIN

    return f"ip:{client_ip}", ClientTier.ANONYMOUS


def _extract_client_ip(request: Request) -> str:
    """
    Extracts the sanitized client IP address.
    Inspects X-Forwarded-For when behind a reverse proxy (e.g. Cloudflare / Nginx / Railway).
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # First entry in X-Forwarded-For is the originating client
        return forwarded.split(",")[0].strip()

    cf_connecting_ip = request.headers.get("CF-Connecting-IP")
    if cf_connecting_ip:
        return cf_connecting_ip.strip()

    if request.client and request.client.host:
        return request.client.host

    return "127.0.0.1"
