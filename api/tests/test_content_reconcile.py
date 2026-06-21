"""Tests for file reconciliation task scheduling."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from models.enums import ProcessingStatus
from services.adapters.base import ContentEntry
from services.content.reconcile import Reconciler


class _DummyTask:
    def __init__(self, *, done: bool = False):
        self._done = done
        self._callbacks = []

    def done(self) -> bool:
        return self._done

    def add_done_callback(self, callback) -> None:
        self._callbacks.append(callback)

    def mark_done(self) -> None:
        self._done = True
        for callback in list(self._callbacks):
            callback(self)


@pytest.fixture(autouse=True)
def _reset_reconcile_background_state():
    Reconciler._background_tasks = {}
    Reconciler._background_task_lock = None
    yield
    Reconciler._background_tasks = {}
    Reconciler._background_task_lock = None


def _folder() -> SimpleNamespace:
    return SimpleNamespace(uuid="folder-1", name="docs")


@pytest.mark.asyncio
async def test_scan_directory_normalizes_adapter_paths():
    """Reconcile compares storage paths in the app's canonical Unicode form."""
    db = AsyncMock()
    reconciler = Reconciler(db)
    adapter = SimpleNamespace(
        list_directory=AsyncMock(
            return_value=[
                ContentEntry(
                    name="20230127_Cafe\u0301Report.pdf",
                    relative_path="reports/20230127_Cafe\u0301Report.pdf",
                    is_dir=False,
                    is_file=True,
                    is_symlink=False,
                    size_bytes=1,
                    modified_time=1.0,
                    change_time=1.0,
                )
            ]
        )
    )
    folder = SimpleNamespace(uuid="folder-1", name="docs", get_adapter=lambda: adapter)

    entries = await reconciler._scan_directory(folder, "reports")

    assert list(entries) == ["reports/20230127_CaféReport.pdf"]
    assert (
        entries["reports/20230127_CaféReport.pdf"].relative_path
        == "reports/20230127_CaféReport.pdf"
    )


@pytest.mark.asyncio
async def test_scan_directory_logs_expected_adapter_failures_with_traceback(caplog):
    db = AsyncMock()
    reconciler = Reconciler(db)
    adapter = SimpleNamespace(
        list_directory=AsyncMock(side_effect=PermissionError("denied"))
    )
    folder = SimpleNamespace(uuid="folder-1", name="docs", get_adapter=lambda: adapter)
    caplog.set_level(logging.WARNING, logger="services.content.reconcile")

    entries = await reconciler._scan_directory(folder, "reports")

    assert entries == {}
    assert "Reconciliation scan failed for docs/reports" in caplog.text
    assert "PermissionError: denied" in caplog.text


@pytest.mark.asyncio
async def test_maybe_reconcile_dedupes_background_tasks(monkeypatch):
    """Repeated stale reads should share one in-flight background reconcile task."""
    db = AsyncMock()
    reconciler = Reconciler(db)
    monkeypatch.setattr(
        "services.content.reconcile.get_record",
        AsyncMock(return_value=SimpleNamespace(last_scanned_at=None)),
    )
    monkeypatch.setattr(reconciler, "_child_record_count", AsyncMock(return_value=3))

    scheduled_coroutines = []
    task = _DummyTask()

    def fake_create_task(coroutine):
        scheduled_coroutines.append(coroutine)
        coroutine.close()
        return task

    monkeypatch.setattr(
        Reconciler,
        "_create_background_task",
        classmethod(lambda cls, coroutine: fake_create_task(coroutine)),
    )

    folder = _folder()
    await reconciler.maybe_reconcile(folder, "reports")
    await reconciler.maybe_reconcile(folder, "reports")

    assert len(scheduled_coroutines) == 1
    assert Reconciler._background_tasks == {(folder.uuid, "reports"): task}


@pytest.mark.asyncio
async def test_completed_background_task_allows_reschedule_without_clobbering_new_task(
    monkeypatch,
):
    """Old task cleanup must not remove a newer replacement task for the same path."""
    db = AsyncMock()
    reconciler = Reconciler(db)
    monkeypatch.setattr(
        "services.content.reconcile.get_record",
        AsyncMock(return_value=SimpleNamespace(last_scanned_at=None)),
    )
    monkeypatch.setattr(reconciler, "_child_record_count", AsyncMock(return_value=2))

    first_task = _DummyTask()
    second_task = _DummyTask()
    task_queue = [first_task, second_task]

    def fake_create_task(coroutine):
        coroutine.close()
        return task_queue.pop(0)

    monkeypatch.setattr(
        Reconciler,
        "_create_background_task",
        classmethod(lambda cls, coroutine: fake_create_task(coroutine)),
    )

    folder = _folder()
    key = (folder.uuid, "reports")

    await reconciler.maybe_reconcile(folder, "reports")
    first_task.mark_done()
    await reconciler.maybe_reconcile(folder, "reports")

    assert Reconciler._background_tasks[key] is second_task

    Reconciler._release_background_task(key, first_task)

    assert Reconciler._background_tasks[key] is second_task


@pytest.mark.asyncio
async def test_remove_stale_records_keeps_active_processing_rows():
    """Reconcile must not delete rows while a worker can still write results."""
    db = AsyncMock()
    reconciler = Reconciler(db)
    folder = _folder()
    delete_content_path = AsyncMock()
    reconciler_delete_service = SimpleNamespace(delete_content_path=delete_content_path)
    queued = SimpleNamespace(
        relative_path="reports/queued.pdf",
        processing_status=ProcessingStatus.QUEUED.value,
        content_item_id="queued-id",
    )
    processing = SimpleNamespace(
        relative_path="reports/processing.pdf",
        processing_status=ProcessingStatus.PROCESSING.value,
        content_item_id="processing-id",
    )
    completed = SimpleNamespace(
        relative_path="reports/completed.pdf",
        processing_status=ProcessingStatus.COMPLETED.value,
        content_item_id="completed-id",
    )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "services.content.reconcile.ContentDeletionService",
        lambda _db: reconciler_delete_service,
    )
    monkeypatch.setattr(reconciler, "_has_active_task", AsyncMock(return_value=False))

    try:
        removed = await reconciler._remove_stale_records(
            {
                queued.relative_path: queued,
                processing.relative_path: processing,
                completed.relative_path: completed,
            },
            seen_paths=set(),
            folder=folder,
            display_path="reports",
            directory_relative_path="reports",
        )
    finally:
        monkeypatch.undo()

    assert removed == 1
    delete_content_path.assert_awaited_once_with(
        folder_uuid="folder-1",
        relative_path="reports/completed.pdf",
        content_item_id="completed-id",
        source="reconcile",
        metadata={"origin": "reconcile"},
    )


@pytest.mark.asyncio
async def test_remove_stale_records_keeps_rows_with_active_queue_tasks(monkeypatch):
    """An active task is authoritative even if the indexed status is stale."""
    db = AsyncMock()
    reconciler = Reconciler(db)
    folder = _folder()
    delete_content_path = AsyncMock()
    reconciler_delete_service = SimpleNamespace(delete_content_path=delete_content_path)
    active_task_record = SimpleNamespace(
        relative_path="reports/active.pdf",
        processing_status=ProcessingStatus.COMPLETED.value,
        content_item_id="active-id",
    )

    monkeypatch.setattr(
        "services.content.reconcile.ContentDeletionService",
        lambda _db: reconciler_delete_service,
    )
    monkeypatch.setattr(reconciler, "_has_active_task", AsyncMock(return_value=True))

    removed = await reconciler._remove_stale_records(
        {active_task_record.relative_path: active_task_record},
        seen_paths=set(),
        folder=folder,
        display_path="reports",
        directory_relative_path="reports",
    )

    assert removed == 0
    delete_content_path.assert_not_awaited()


@pytest.mark.asyncio
async def test_child_record_count_excludes_directory_record_itself():
    """Root reconcile should not count the directory placeholder as child content."""
    result = MagicMock()
    result.scalar.return_value = 0
    db = AsyncMock()
    db.execute.return_value = result
    reconciler = Reconciler(db)

    await reconciler._child_record_count("folder-1", "")

    stmt = db.execute.await_args.args[0]
    compiled = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "indexed_content_items.parent_path = ''" in compiled
    assert "indexed_content_items.relative_path != ''" in compiled


@pytest.mark.asyncio
async def test_remove_stale_records_skips_directory_self_record_at_root():
    """Root reconcile must never delete the connector via an empty relative path."""
    db = AsyncMock()
    reconciler = Reconciler(db)
    folder = _folder()
    delete_content_path = AsyncMock()
    reconciler_delete_service = SimpleNamespace(delete_content_path=delete_content_path)
    root_record = SimpleNamespace(
        relative_path="",
        processing_status=None,
        content_item_id="root-id",
    )
    completed = SimpleNamespace(
        relative_path="reports/completed.pdf",
        processing_status=ProcessingStatus.COMPLETED.value,
        content_item_id="completed-id",
    )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "services.content.reconcile.ContentDeletionService",
        lambda _db: reconciler_delete_service,
    )
    monkeypatch.setattr(reconciler, "_has_active_task", AsyncMock(return_value=False))

    try:
        removed = await reconciler._remove_stale_records(
            {
                root_record.relative_path: root_record,
                completed.relative_path: completed,
            },
            seen_paths=set(),
            folder=folder,
            display_path="(root)",
            directory_relative_path="",
        )
    finally:
        monkeypatch.undo()

    assert removed == 1
    delete_content_path.assert_awaited_once_with(
        folder_uuid="folder-1",
        relative_path="reports/completed.pdf",
        content_item_id="completed-id",
        source="reconcile",
        metadata={"origin": "reconcile"},
    )
