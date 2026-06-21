"""Structured logging configuration for the backend."""

import json
import logging
import sys
import uuid
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Optional

from config import get_settings

correlation_id_var: ContextVar[Optional[str]] = ContextVar(
    "correlation_id", default=None
)


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        correlation_id = correlation_id_var.get()
        if correlation_id:
            log_entry["correlation_id"] = correlation_id

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "extra_data"):
            log_entry.update(record.extra_data)

        return json.dumps(log_entry)


class PlainFormatter(logging.Formatter):
    """Plain text formatter for development."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as plain text."""
        correlation_id = correlation_id_var.get()
        prefix = f"[{correlation_id[:8]}] " if correlation_id else ""
        return f"{record.levelname:8s} {prefix}{record.name}: {record.getMessage()}"


def setup_logging() -> None:
    """Configure logging based on settings."""
    settings = get_settings()

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if settings.LOG_JSON_FORMAT:
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(PlainFormatter())

    root_logger.addHandler(handler)

    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


class LoggingContext:
    """Context manager for scoped correlation IDs."""

    def __init__(self, correlation_id: Optional[str] = None):
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self._token: Token[Optional[str]] | None = None

    def __enter__(self) -> str:
        self._token = correlation_id_var.set(self.correlation_id)
        return self.correlation_id

    def __exit__(self, *args) -> None:
        if self._token is not None:
            correlation_id_var.reset(self._token)


def get_logger(
    name: str, correlation_id: Optional[str] = None
) -> logging.LoggerAdapter:
    """
    Get a logger with optional correlation ID.

    Args:
        name: Logger name (usually __name__)
        correlation_id: Optional correlation ID to include in all log messages

    Returns:
        LoggerAdapter with correlation ID support
    """
    logger = logging.getLogger(name)

    class CorrelationAdapter(logging.LoggerAdapter):
        def process(self, msg, kwargs):
            cid = correlation_id or correlation_id_var.get()
            if cid:
                kwargs.setdefault("extra", {})
                kwargs["extra"]["extra_data"] = {"correlation_id": cid}
            return msg, kwargs

    return CorrelationAdapter(logger, {})


def generate_correlation_id() -> str:
    """Generate a new correlation ID."""
    return str(uuid.uuid4())
