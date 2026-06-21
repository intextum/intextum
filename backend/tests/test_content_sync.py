"""Tests for shared file sync helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from models.enums import ProcessingStatus
from models.task_queue import EnqueueProcessTask
from services.content.sync import (
    EffectiveViewers,
    ObservedContentItem,
    build_effective_viewers,
    sync_observed_file,
    upsert_directory_record,
)
from services.utils import compute_content_item_id


def _folder(*, auto_process_new: bool = True):
    return SimpleNamespace(
        uuid="folder-1",
        name="docs",
        auto_process_new=auto_process_new,
    )


def _record(
    *,
    modified_time: float = 10.0,
    change_time: float = 20.0,
    size_bytes: int = 100,
    processing_status: str | None = ProcessingStatus.COMPLETED,
):
    return SimpleNamespace(
        modified_time=modified_time,
        change_time=change_time,
        size_bytes=size_bytes,
        processing_status=processing_status,
    )


def _observed_file(
    *,
    modified_time: float = 10.0,
    change_time: float = 20.0,
    size_bytes: int = 100,
):
    return ObservedContentItem(
        content_item_id="file-1",
        relative_path="reports/summary.pdf",
        modified_time=modified_time,
        change_time=change_time,
        size_bytes=size_bytes,
        is_symlink=False,
        file_extension=".pdf",
    )


def test_build_effective_viewers_normalizes_empty_acl_lists():
    """Empty ACL lists should serialize as None for DB persistence."""
    assert build_effective_viewers([], []) == EffectiveViewers(
        allowed=[],
        denied=[],
        allowed_or_none=None,
        denied_or_none=None,
    )


@pytest.mark.asyncio
async def test_upsert_directory_record_uses_shared_acl_shape(monkeypatch):
    """Directory sync should go through the shared upsert helper with normalized ACLs."""
    upsert_directory_entry = AsyncMock()
    monkeypatch.setattr(
        "services.content.sync.upsert_directory_entry",
        upsert_directory_entry,
    )

    db = AsyncMock()
    folder = _folder()

    await upsert_directory_record(
        db,
        folder,
        "reports",
        False,
        build_effective_viewers(["sub:alice"], []),
    )

    assert upsert_directory_entry.await_args.args == (
        db,
        compute_content_item_id(folder.uuid, "reports"),
        "folder-1",
        "reports",
    )
    assert upsert_directory_entry.await_args.kwargs == {
        "allowed_viewers": ["sub:alice"],
        "denied_viewers": None,
        "is_symlink": False,
        "auto_commit": False,
    }


@pytest.mark.asyncio
async def test_sync_observed_file_skips_unchanged_records(monkeypatch):
    """No-op syncs should not touch the DB or task queue."""
    upsert_indexed_content_item = AsyncMock()
    monkeypatch.setattr(
        "services.content.sync.upsert_indexed_content_item", upsert_indexed_content_item
    )

    task_svc = SimpleNamespace(enqueue_process=AsyncMock())
    result = await sync_observed_file(
        db=AsyncMock(),
        task_svc=task_svc,
        folder=_folder(),
        observed_file=_observed_file(),
        record=_record(),
        viewers=build_effective_viewers(["sub:alice"], []),
    )

    assert result.changed is False
    assert result.enqueued is False
    upsert_indexed_content_item.assert_not_awaited()
    task_svc.enqueue_process.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_observed_file_upserts_and_enqueues_on_content_change(monkeypatch):
    """Changed file content should update the index row and enqueue processing."""
    upsert_indexed_content_item = AsyncMock()
    monkeypatch.setattr(
        "services.content.sync.upsert_indexed_content_item", upsert_indexed_content_item
    )

    task_svc = SimpleNamespace(enqueue_process=AsyncMock())
    result = await sync_observed_file(
        db=AsyncMock(),
        task_svc=task_svc,
        folder=_folder(auto_process_new=True),
        observed_file=_observed_file(modified_time=11.0),
        record=_record(),
        viewers=build_effective_viewers(["sub:alice"], ["sub:bob"]),
    )

    assert result.changed is True
    assert result.content_changed is True
    assert result.enqueued is True
    upsert_indexed_content_item.assert_awaited_once()
    task_svc.enqueue_process.assert_awaited_once()
    request = task_svc.enqueue_process.await_args.args[0]
    assert isinstance(request, EnqueueProcessTask)
    assert request.metadata.allowed_viewers == ["sub:alice"]
    assert request.metadata.denied_viewers == ["sub:bob"]


@pytest.mark.asyncio
async def test_sync_observed_file_requeues_existing_queued_records_when_enabled(
    monkeypatch,
):
    """Reconcile mode should be able to re-enqueue files already marked QUEUED."""
    upsert_indexed_content_item = AsyncMock()
    monkeypatch.setattr(
        "services.content.sync.upsert_indexed_content_item", upsert_indexed_content_item
    )

    task_svc = SimpleNamespace(enqueue_process=AsyncMock())
    result = await sync_observed_file(
        db=AsyncMock(),
        task_svc=task_svc,
        folder=_folder(auto_process_new=True),
        observed_file=_observed_file(),
        record=_record(processing_status=ProcessingStatus.QUEUED),
        viewers=build_effective_viewers(["sub:alice"], []),
        requeue_if_status_queued=True,
    )

    assert result.changed is False
    assert result.enqueued is True
    upsert_indexed_content_item.assert_not_awaited()
    task_svc.enqueue_process.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_observed_file_does_not_requeue_queued_records_by_default(
    monkeypatch,
):
    """Watcher mode should not re-enqueue already-queued records without a content change."""
    upsert_indexed_content_item = AsyncMock()
    monkeypatch.setattr(
        "services.content.sync.upsert_indexed_content_item", upsert_indexed_content_item
    )

    task_svc = SimpleNamespace(enqueue_process=AsyncMock())
    result = await sync_observed_file(
        db=AsyncMock(),
        task_svc=task_svc,
        folder=_folder(auto_process_new=True),
        observed_file=_observed_file(),
        record=_record(processing_status=ProcessingStatus.QUEUED),
        viewers=build_effective_viewers(["sub:alice"], []),
    )

    assert result.changed is False
    assert result.enqueued is False
    upsert_indexed_content_item.assert_not_awaited()
    task_svc.enqueue_process.assert_not_awaited()
