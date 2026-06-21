"""Structured logging configuration for the worker service."""

import json
import logging
import sys
import uuid
from collections.abc import MutableMapping
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def generate_correlation_id() -> str:
    """Generate a new correlation ID."""
    return str(uuid.uuid4())[:8]


def get_correlation_id() -> str | None:
    """Get the current correlation ID from context."""
    return correlation_id_var.get()


def set_correlation_id(correlation_id: str) -> None:
    """Set the correlation ID in context."""
    correlation_id_var.set(correlation_id)


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        correlation_id = get_correlation_id()
        if correlation_id:
            log_data["correlation_id"] = correlation_id

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "__dict__"):
            extra_fields = {
                k: v
                for k, v in record.__dict__.items()
                if k
                not in {
                    "name",
                    "msg",
                    "args",
                    "created",
                    "filename",
                    "funcName",
                    "levelname",
                    "levelno",
                    "lineno",
                    "module",
                    "msecs",
                    "pathname",
                    "process",
                    "processName",
                    "relativeCreated",
                    "stack_info",
                    "exc_info",
                    "exc_text",
                    "thread",
                    "threadName",
                    "taskName",
                    "message",
                }
            }
            if extra_fields:
                log_data["extra"] = extra_fields

        return json.dumps(log_data)


class CorrelatedLogger(logging.LoggerAdapter):
    """Logger adapter that includes correlation ID in all log messages."""

    def __init__(self, logger: logging.Logger, correlation_id: str):
        super().__init__(logger, {})
        self.correlation_id = correlation_id

    def process(
        self, msg: object, kwargs: MutableMapping[str, Any]
    ) -> tuple[object, MutableMapping[str, Any]]:
        extra = kwargs.get("extra")
        if not isinstance(extra, dict):
            extra = {}
        extra["correlation_id"] = self.correlation_id
        kwargs["extra"] = extra
        return msg, kwargs


def get_logger(name: str, correlation_id: str | None = None) -> logging.LoggerAdapter:
    """Get a logger with optional correlation ID.

    Args:
        name: Logger name (typically __name__)
        correlation_id: Optional correlation ID, generates new one if not provided

    Returns:
        Logger adapter with correlation context
    """
    logger = logging.getLogger(name)
    cid = correlation_id or get_correlation_id() or generate_correlation_id()
    return CorrelatedLogger(logger, cid)


def configure_logging(json_format: bool = True, level: str = "INFO") -> None:
    """Configure logging for the worker service.

    Args:
        json_format: Use JSON structured logging if True, human-readable if False
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)

    if json_format:
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(levelname)s - [%(correlation_id)s] %(name)s - %(message)s",
                defaults={"correlation_id": "no-correlation"},
            )
        )

    root_logger.addHandler(handler)


class LoggingContext:
    """Context manager for scoped correlation IDs."""

    def __init__(self, correlation_id: str | None = None):
        self.correlation_id = correlation_id or generate_correlation_id()
        self._token: Token[str | None] | None = None

    def __enter__(self) -> str:
        self._token = correlation_id_var.set(self.correlation_id)
        return self.correlation_id

    def __exit__(self, *args) -> None:
        if self._token is not None:
            correlation_id_var.reset(self._token)
