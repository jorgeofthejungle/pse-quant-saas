"""
pse_quant/telemetry/context.py — Asynchronous Trace Context & Correlation ID Propagation
PSE Quant SaaS (v2 Rebuild) — Lab 10

Provides thread-safe and asyncio-safe context propagation across coroutines,
database transactions, and background workers using Python's contextvars.
"""

from __future__ import annotations
import uuid
from contextvars import ContextVar, Token
from typing import Optional, Dict, Any

_correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="")
_trace_metadata_ctx: ContextVar[Dict[str, Any]] = ContextVar("trace_metadata", default={})


def generate_correlation_id(prefix: str = "corr_") -> str:
    """Generates a high-entropy, collision-resistant correlation identifier."""
    return f"{prefix}{uuid.uuid4().hex[:16]}"


def get_correlation_id() -> str:
    """Retrieves the active correlation ID from the ambient execution context."""
    return _correlation_id_ctx.get()


def set_correlation_id(correlation_id: str) -> Token:
    """Sets the active correlation ID in the current execution context."""
    return _correlation_id_ctx.set(correlation_id)


def reset_correlation_id(token: Token) -> None:
    """Resets the correlation ID back to its previous state using the token."""
    _correlation_id_ctx.reset(token)


def get_trace_metadata() -> Dict[str, Any]:
    """Retrieves ambient trace metadata (e.g. path, method, user_id)."""
    return dict(_trace_metadata_ctx.get())


def set_trace_metadata(metadata: Dict[str, Any]) -> Token:
    """Sets ambient trace metadata in the current execution context."""
    return _trace_metadata_ctx.set(metadata)


def reset_trace_metadata(token: Token) -> None:
    """Resets trace metadata back to its previous state."""
    _trace_metadata_ctx.reset(token)
