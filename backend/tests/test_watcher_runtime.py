"""Tests for watcher runtime helper functions."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from watchfiles import Change

from models.connector_types import LocalFsDataConnector
from services.adapters.base import ContentEntry
from services.watcher_runtime.local import _handle_directory_change
from services.watcher_runtime.remote import (
    _collect_entries_recursive,
    _remove_s3_missing_records,
)
from services.watcher_runtime.scan import _iter_entries_recursive
from services.watcher_runtime.shared import (
    _safe_relative_path,
    _visible_entries_by_path,
)


def test_safe_relative_path_returns_folder_relative_path(tmp_path):
    folder_root = tmp_path / "source"
    folder_root.mkdir()
    nested_file = folder_root / "nested" / "report.pdf"
    nested_file.parent.mkdir()
    nested_file.write_text("hello", encoding="utf-8")

    folder = LocalFsDataConnector(uuid="source-1", name="source", path=str(folder_root))

    relative = _safe_relative_path(nested_file, folder)

    assert relative == "nested/report.pdf"


def test_visible_entries_by_path_excludes_hidden_entries():
    entries = [
        ContentEntry(
            name="report.pdf",
            relative_path="report.pdf",
            is_dir=False,
            is_file=True,
            is_symlink=False,
            size_bytes=1,
            modified_time=1.0,
            change_time=1.0,
        ),
        ContentEntry(
            name=".hidden.pdf",
            relative_path=".hidden.pdf",
            is_dir=False,
            is_file=True,
            is_symlink=False,
            size_bytes=1,
            modified_time=1.0,
            change_time=1.0,
        ),
    ]

    visible = _visible_entries_by_path(entries)

    assert visible == {
        "report.pdf": entries[0],
    }


@pytest.mark.asyncio
async def test_scan_recursive_logs_list_failures_with_traceback(caplog):
    folder = SimpleNamespace(
        name="docs",
        get_adapter=lambda: SimpleNamespace(
            list_directory=AsyncMock(side_effect=RuntimeError("scan failed"))
        ),
    )
    caplog.set_level(logging.WARNING, logger="services.watcher_runtime.scan")

    entries = [entry async for entry in _iter_entries_recursive(folder)]

    assert entries == []
    assert "Failed to list docs/" in caplog.text
    assert "RuntimeError: scan failed" in caplog.text


@pytest.mark.asyncio
async def test_remote_recursive_logs_list_failures_with_traceback(caplog):
    folder = SimpleNamespace(
        name="s3-docs",
        get_adapter=lambda: SimpleNamespace(
            list_directory=AsyncMock(side_effect=RuntimeError("s3 failed"))
        ),
    )
    caplog.set_level(logging.WARNING, logger="services.watcher_runtime.remote")

    entries = await _collect_entries_recursive(folder)

    assert entries == []
    assert "Failed to list s3-docs/" in caplog.text
    assert "RuntimeError: s3 failed" in caplog.text


@pytest.mark.asyncio
async def test_handle_directory_change_uses_content_deletion_service():
    delete_content_path = AsyncMock()
    get_indexed_content_item = AsyncMock(
        return_value=SimpleNamespace(
            content_item_id="dir-1",
            relative_path="nested",
            is_dir=True,
        )
    )

    folder = LocalFsDataConnector(uuid="source-1", name="source", path="/tmp/source")
    event = SimpleNamespace(
        db=AsyncMock(),
        task_svc=AsyncMock(),
        folder=folder,
        content_item_id="dir-1",
        relative_path="nested",
    )

    handled = await _handle_directory_change(
        change_type=Change.deleted,
        path_obj=SimpleNamespace(is_dir=lambda: False),
        event=event,
        get_indexed_content_item_fn=get_indexed_content_item,
        delete_service_factory=lambda _db: SimpleNamespace(
            delete_content_path=delete_content_path
        ),
    )

    assert handled is True
    delete_content_path.assert_awaited_once_with(
        folder_uuid="source-1",
        relative_path="nested",
        content_item_id="dir-1",
        source="watcher",
        metadata={"origin": "local_watcher"},
    )


@pytest.mark.asyncio
async def test_remove_s3_missing_records_deletes_only_stale_roots():
    delete_content_path = AsyncMock()

    folder = SimpleNamespace(uuid="folder-1", name="docs")
    db_records = {
        "reports": SimpleNamespace(relative_path="reports", is_dir=True),
        "reports/file.pdf": SimpleNamespace(
            relative_path="reports/file.pdf", is_dir=False
        ),
        "reports/nested/child.pdf": SimpleNamespace(
            relative_path="reports/nested/child.pdf",
            is_dir=False,
        ),
        "other.txt": SimpleNamespace(relative_path="other.txt", is_dir=False),
    }

    removed = await _remove_s3_missing_records(
        AsyncMock(),
        folder,
        db_records,
        current_paths={},
        delete_service_factory=lambda _db: SimpleNamespace(
            delete_content_path=delete_content_path
        ),
    )

    assert removed is True
    assert delete_content_path.await_count == 2
    deleted_paths = {
        call.kwargs["relative_path"] for call in delete_content_path.await_args_list
    }
    assert deleted_paths == {"other.txt", "reports"}
