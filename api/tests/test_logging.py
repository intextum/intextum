"""Tests for logging configuration."""

import json
import logging
from logging_config import (
    StructuredFormatter,
    PlainFormatter,
    LoggingContext,
    get_logger,
    correlation_id_var,
    generate_correlation_id,
)


class TestStructuredFormatter:
    """Tests for JSON structured formatter."""

    def test_formats_as_json(self):
        """Formats log records as valid JSON."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        data = json.loads(output)

        assert data["level"] == "INFO"
        assert data["logger"] == "test"
        assert data["message"] == "Test message"
        assert "timestamp" in data

    def test_includes_correlation_id(self):
        """Includes correlation ID when set."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        token = correlation_id_var.set("test-correlation-123")
        try:
            output = formatter.format(record)
            data = json.loads(output)
            assert data["correlation_id"] == "test-correlation-123"
        finally:
            correlation_id_var.reset(token)

    def test_includes_exception_info(self):
        """Includes exception information when present."""
        formatter = StructuredFormatter()

        try:
            raise ValueError("Test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )

        output = formatter.format(record)
        data = json.loads(output)

        assert "exception" in data
        assert "ValueError" in data["exception"]


class TestPlainFormatter:
    """Tests for plain text formatter."""

    def test_formats_as_plain_text(self):
        """Formats log records as plain text."""
        formatter = PlainFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)

        assert "INFO" in output
        assert "test" in output
        assert "Test message" in output

    def test_includes_correlation_id_prefix(self):
        """Includes correlation ID prefix when set."""
        formatter = PlainFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        token = correlation_id_var.set("abcd1234-5678-90ab-cdef")
        try:
            output = formatter.format(record)
            assert "[abcd1234]" in output
        finally:
            correlation_id_var.reset(token)


class TestLoggingContext:
    """Tests for LoggingContext context manager."""

    def test_sets_correlation_id(self):
        """Sets correlation ID within context."""
        with LoggingContext("test-id-123") as cid:
            assert cid == "test-id-123"
            assert correlation_id_var.get() == "test-id-123"

    def test_resets_correlation_id_after_context(self):
        """Resets correlation ID after context exits."""
        original = correlation_id_var.get()

        with LoggingContext("temp-id"):
            pass

        assert correlation_id_var.get() == original

    def test_generates_id_when_not_provided(self):
        """Generates correlation ID when not provided."""
        with LoggingContext() as cid:
            assert cid is not None
            assert len(cid) > 0


class TestGetLogger:
    """Tests for get_logger function."""

    def test_returns_logger_adapter(self):
        """Returns a LoggerAdapter instance."""
        logger = get_logger("test")
        assert isinstance(logger, logging.LoggerAdapter)

    def test_logs_with_correlation_id(self):
        """Logger includes correlation ID in output."""
        logger = get_logger("test", correlation_id="explicit-id")
        assert logger is not None


class TestGenerateCorrelationId:
    """Tests for generate_correlation_id function."""

    def test_generates_uuid(self):
        """Generates a valid UUID string."""
        cid = generate_correlation_id()
        assert len(cid) == 36
        assert cid.count("-") == 4

    def test_generates_unique_ids(self):
        """Generates unique IDs on each call."""
        ids = [generate_correlation_id() for _ in range(100)]
        assert len(set(ids)) == 100
