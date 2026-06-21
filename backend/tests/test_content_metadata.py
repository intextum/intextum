"""Tests for shared content metadata coercion helpers."""

from services.content.metadata import metadata_float, metadata_int
from services.utils import get_content_item_metadata


def test_metadata_float_accepts_numeric_strings_and_defaults_bad_shapes():
    assert metadata_float({"modified_time": "12.5"}, "modified_time") == 12.5
    assert metadata_float({"modified_time": ["12.5"]}, "modified_time") == 0.0
    assert metadata_float({}, "modified_time", default=7.5) == 7.5


def test_metadata_int_accepts_numeric_strings_and_defaults_bad_shapes():
    assert metadata_int({"size_bytes": "42"}, "size_bytes") == 42
    assert metadata_int({"size_bytes": {"value": 42}}, "size_bytes") == 0
    assert metadata_int({}, "size_bytes", default=7) == 7


def test_get_content_item_metadata_defaults_missing_files_to_empty_dict(tmp_path):
    assert get_content_item_metadata(tmp_path / "missing.pdf") == {}
