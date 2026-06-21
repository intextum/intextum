"""Tests for centralized content deletion helpers."""

from types import SimpleNamespace

from services.content.deletion import _cleanup_content_item_ids


def test_cleanup_content_item_ids_deduplicates_file_records_and_skips_dirs():
    records = [
        SimpleNamespace(content_item_id="dir-1", is_dir=True),
        SimpleNamespace(content_item_id="file-1", is_dir=False),
        SimpleNamespace(content_item_id="file-1", is_dir=False),
        SimpleNamespace(content_item_id="file-2", is_dir=False),
    ]

    assert _cleanup_content_item_ids(records, "fallback") == ("file-1", "file-2")


def test_cleanup_content_item_ids_uses_fallback_without_file_records():
    assert _cleanup_content_item_ids([], "fallback") == ("fallback",)
