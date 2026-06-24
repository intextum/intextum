"""Tests for initial-scan progress tracking (data_source_scan_status writes)."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import services.watcher_runtime.scan as scan
from services.adapters.base import ContentEntry


def _entry(name: str, *, is_dir: bool) -> ContentEntry:
    return ContentEntry(
        name=name,
        relative_path=name,
        is_dir=is_dir,
        is_file=not is_dir,
        is_symlink=False,
        size_bytes=0,
        modified_time=0.0,
        change_time=0.0,
    )


def _patch_scan_dependencies(monkeypatch, status_calls):
    """Stub out DB/session/sync internals so only status tracking is exercised."""

    @asynccontextmanager
    async def fake_session(_factory, _context):
        yield SimpleNamespace(commit=AsyncMock())

    async def fake_upsert_status(_db, connector_uuid, **fields):
        status_calls.append(fields)

    monkeypatch.setattr(scan, "rls_session", fake_session)
    monkeypatch.setattr(scan, "_upsert_scan_status", fake_upsert_status)
    monkeypatch.setattr(scan, "TaskQueueService", lambda _db: SimpleNamespace())
    viewers = SimpleNamespace(allowed_or_none=None, denied_or_none=None)
    monkeypatch.setattr(scan, "_get_effective_viewers", AsyncMock(return_value=viewers))
    monkeypatch.setattr(scan, "upsert_directory_entry", AsyncMock())
    monkeypatch.setattr(
        scan,
        "get_settings",
        lambda: SimpleNamespace(SCAN_COMMIT_EVERY=1, SCAN_HEARTBEAT_SECONDS=1e9),
    )


@pytest.mark.asyncio
async def test_scan_records_progress_and_marks_done(monkeypatch):
    status_calls: list[dict] = []
    _patch_scan_dependencies(monkeypatch, status_calls)

    # Two files (one queued, one unchanged) plus one directory.
    async def fake_scan_entry(_source, entry):
        if entry.is_dir:
            return 0, 0
        return (1, 0) if entry.name == "new.pdf" else (0, 1)

    monkeypatch.setattr(scan, "_scan_entry", fake_scan_entry)

    folder = SimpleNamespace(
        uuid="conn-1",
        name="docs",
        connector_type="s3",
        poll_interval_seconds=30,
    )
    entries = [
        _entry("sub", is_dir=True),
        _entry("new.pdf", is_dir=False),
        _entry("old.pdf", is_dir=False),
    ]

    count, skipped = await scan._scan_existing_entries(folder, entries)

    assert (count, skipped) == (1, 1)
    # First write announces scanning, last write marks done with final totals.
    assert status_calls[0]["state"] == "scanning"
    assert status_calls[-1]["state"] == "done"
    assert status_calls[-1]["dirs"] == 1
    assert status_calls[-1]["files_queued"] == 1
    assert status_calls[-1]["files_unchanged"] == 1
    assert status_calls[-1]["finished_at"] is not None
    # The completed scan records its config signature so a restart can skip it.
    assert status_calls[-1]["signature"] == scan.scan_signature_key(folder)


@pytest.mark.asyncio
async def test_mark_scan_failed_writes_failed_state(monkeypatch):
    status_calls: list[dict] = []

    @asynccontextmanager
    async def fake_session(_factory, _context):
        yield SimpleNamespace(commit=AsyncMock())

    async def fake_upsert_status(_db, connector_uuid, **fields):
        status_calls.append(fields)

    monkeypatch.setattr(scan, "rls_session", fake_session)
    monkeypatch.setattr(scan, "_upsert_scan_status", fake_upsert_status)

    await scan.mark_scan_failed("conn-1")

    assert status_calls == [
        {"state": "failed", "finished_at": status_calls[0]["finished_at"]}
    ]
    assert status_calls[0]["finished_at"] is not None
