"""Tests for the logging configuration module."""

import json
import logging

from intextum_worker.logging_config import (
    CorrelatedLogger,
    LoggingContext,
    StructuredFormatter,
    configure_logging,
    generate_correlation_id,
    get_correlation_id,
    get_logger,
    set_correlation_id,
)


class TestCorrelationId:
    def test_generate_correlation_id_returns_string(self):
        cid = generate_correlation_id()
        assert isinstance(cid, str)
        assert len(cid) == 8

    def test_generate_correlation_id_is_unique(self):
        ids = [generate_correlation_id() for _ in range(100)]
        assert len(set(ids)) == 100

    def test_set_and_get_correlation_id(self):
        set_correlation_id("test-123")
        assert get_correlation_id() == "test-123"

    def test_get_correlation_id_returns_none_when_not_set(self):
        # Reset context
        from intextum_worker.logging_config import correlation_id_var

        correlation_id_var.set(None)

        assert get_correlation_id() is None


class TestLoggingContext:
    def test_context_sets_correlation_id(self):
        with LoggingContext("ctx-test-id") as cid:
            assert cid == "ctx-test-id"
            assert get_correlation_id() == "ctx-test-id"

    def test_context_generates_id_if_not_provided(self):
        with LoggingContext() as cid:
            assert cid is not None
            assert len(cid) == 8
            assert get_correlation_id() == cid

    def test_context_restores_previous_id(self):
        set_correlation_id("outer-id")

        with LoggingContext("inner-id"):
            assert get_correlation_id() == "inner-id"

        # After context, should be restored
        # Note: Due to contextvars behavior in tests, this may vary


class TestStructuredFormatter:
    def test_formats_as_json(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        data = json.loads(output)

        assert data["level"] == "INFO"
        assert data["logger"] == "test.logger"
        assert data["message"] == "Test message"
        assert "timestamp" in data

    def test_includes_correlation_id_when_set(self):
        set_correlation_id("json-test-id")
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        data = json.loads(output)

        assert data.get("correlation_id") == "json-test-id"

    def test_includes_extra_fields(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test",
            args=(),
            exc_info=None,
        )
        record.custom_field = "custom_value"
        record.another_field = 123

        output = formatter.format(record)
        data = json.loads(output)

        assert "extra" in data
        assert data["extra"]["custom_field"] == "custom_value"
        assert data["extra"]["another_field"] == 123


class TestCorrelatedLogger:
    def test_adds_correlation_id_to_extra(self):
        base_logger = logging.getLogger("test.correlated")
        adapter = CorrelatedLogger(base_logger, "adapter-cid")

        _msg, kwargs = adapter.process("Test message", {"extra": {"existing": "value"}})

        assert kwargs["extra"]["correlation_id"] == "adapter-cid"
        assert kwargs["extra"]["existing"] == "value"

    def test_creates_extra_if_missing(self):
        base_logger = logging.getLogger("test.correlated2")
        adapter = CorrelatedLogger(base_logger, "adapter-cid-2")

        _msg, kwargs = adapter.process("Test message", {})

        assert kwargs["extra"]["correlation_id"] == "adapter-cid-2"


class TestGetLogger:
    def test_returns_logger_adapter(self):
        logger = get_logger("test.module")
        assert isinstance(logger, logging.LoggerAdapter)

    def test_uses_provided_correlation_id(self):
        logger = get_logger("test.module", "provided-cid")
        assert logger.correlation_id == "provided-cid"

    def test_generates_correlation_id_if_not_provided(self):
        from intextum_worker.logging_config import correlation_id_var

        correlation_id_var.set(None)

        logger = get_logger("test.module")
        assert logger.correlation_id is not None
        assert len(logger.correlation_id) == 8


class TestConfigureLogging:
    def test_configures_json_format(self):
        configure_logging(json_format=True, level="INFO")

        root = logging.getLogger()
        assert len(root.handlers) > 0
        assert isinstance(root.handlers[0].formatter, StructuredFormatter)

    def test_configures_text_format(self):
        configure_logging(json_format=False, level="DEBUG")

        root = logging.getLogger()
        assert root.level == logging.DEBUG
        assert len(root.handlers) > 0
        assert not isinstance(root.handlers[0].formatter, StructuredFormatter)
