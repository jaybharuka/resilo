"""
Structured JSON logging configuration for ELK Stack integration.
All logs are output as JSON with correlation IDs for request tracing.
"""

import logging
import json
import sys
from pythonjsonlogger import jsonlogger
from contextvars import ContextVar

# Context variable to store correlation ID per request
correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


class CorrelationIdFilter(logging.Filter):
    """Add correlation ID to all log records."""
    
    def filter(self, record):
        record.correlation_id = correlation_id.get()
        return True


def setup_json_logging(logger_name: str = None) -> logging.Logger:
    """
    Configure a logger to output JSON format with correlation IDs.
    
    Args:
        logger_name: Name of the logger (defaults to root logger)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Create JSON handler
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        fmt="%(timestamp)s %(level)s %(name)s %(message)s %(correlation_id)s",
        timestamp=True,
    )
    handler.setFormatter(formatter)
    
    # Add correlation ID filter
    handler.addFilter(CorrelationIdFilter())
    
    logger.addHandler(handler)
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get or create a JSON-configured logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        setup_json_logging(name)
    return logger


def set_correlation_id(request_id: str) -> None:
    """Set the correlation ID for the current request context."""
    correlation_id.set(request_id)


def get_correlation_id() -> str:
    """Get the current request's correlation ID."""
    return correlation_id.get()
