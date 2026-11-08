"""
pse_quant/telemetry/logging.py — Structured JSON Logging Engine
PSE Quant SaaS (v2 Rebuild) — Lab 10

Serializes application and access logs into machine-readable JSON objects
automatically correlated with active trace identifiers.
"""

from __future__ import annotations
import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Any, Dict

from pse_quant.telemetry.context import get_correlation_id, get_trace_metadata


class CorrelationIdFilter(logging.Filter):
    """Logging filter that injects the ambient correlation ID into LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id() or "-"
        return True


class StructuredJsonFormatter(logging.Formatter):
    """
    JSON log formatter conforming to cloud-native observability standards
    (AWS CloudWatch, Datadog, Grafana Loki, Google Cloud Logging).
    """

    def format(self, record: logging.LogRecord) -> str:
        corr_id = getattr(record, "correlation_id", None) or get_correlation_id()
        trace_meta = get_trace_metadata()

        log_payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": corr_id if corr_id else None,
        }

        # Merge ambient trace metadata if present
        if trace_meta:
            log_payload["trace"] = trace_meta

        # Merge standard extra fields if passed via extra={...}
        for attr in ("path", "method", "status_code", "duration_ms", "client_ip", "user_id"):
            val = getattr(record, attr, None)
            if val is not None:
                log_payload[attr] = val

        # Handle exception traces cleanly
        if record.exc_info:
            log_payload["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else "Exception",
                "message": str(record.exc_info[1]) if record.exc_info[1] else "",
                "stack": traceback.format_exception(*record.exc_info),
            }

        return json.dumps(log_payload, default=str)


def create_json_handler(level: int = logging.INFO) -> logging.Handler:
    """Creates a StreamHandler configured with StructuredJsonFormatter and CorrelationIdFilter."""
    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(StructuredJsonFormatter())
    handler.addFilter(CorrelationIdFilter())
    return handler
