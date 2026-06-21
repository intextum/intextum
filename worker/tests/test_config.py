"""Tests for worker configuration parsing."""

import pytest

from config import parse_capabilities


def test_parse_capabilities_accepts_comma_string():
    assert parse_capabilities("document, video,image") == [
        "document",
        "video",
        "image",
    ]


def test_parse_capabilities_accepts_json_array_string():
    assert parse_capabilities('["document", "image"]') == ["document", "image"]


def test_parse_capabilities_accepts_empty_string():
    assert parse_capabilities("") == []


def test_parse_capabilities_rejects_invalid_values():
    with pytest.raises(ValueError, match="Invalid CAPABILITIES"):
        parse_capabilities("document,unknown")
