"""
config/logger.py -- Structured JSON logging for all AIOps services.

Usage:
    from config.logger import get_logger
    logger = get_logger(__name__)
    logger.info("User logged in", extra={"user_id": user_id})
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone

try:
    from opentelemetry import trace as _otel_trace
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False


def _current_trace_context() -> dict:
    """Return trace_id and span_id from the active OTEL span, or empty dict."""
    if not _OTEL_AVAILABLE:
        return {}
    span = _otel_trace.get_current_span()
    ctx = span.get_span_context()
    if ctx is None or not ctx.is_valid:
        return {}
    return {
        "trace_id": format(ctx.trace_id, "032x"),
        "span_id":  format(ctx.span_id, "016x"),
    }


class JSONFormatter(logging.Formatter):
    """Emits one JSON object per log record to stdout for Promtail/Loki ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level":     record.levelname,
            "service":   record.name,
            "message":   record.getMessage(),
            "file":      record.filename,
            "line":      record.lineno,
        }
        entry.update(_current_trace_context())
        # Merge any extra fields passed via extra={...}
        for key, val in record.__dict__.items():
            if key not in (
                "args", "created", "exc_info", "exc_text", "filename",
                "funcName", "levelname", "levelno", "lineno", "message",
                "module", "msecs", "msg", "name", "pathname", "process",
                "processName", "relativeCreated", "stack_info", "thread",
                "threadName",
            ):
                entry[key] = val
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def get_logger(name: str) -> logging.Logger:
    """
    Return a logger that writes structured JSON to stdout.
    Safe to call multiple times — handlers are not duplicated.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    logger.propagate = False
    return logger
