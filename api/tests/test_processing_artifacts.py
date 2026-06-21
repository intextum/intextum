"""Tests for task-scoped processing artifact staging and promotion."""

from datetime import datetime, timezone
from io import BytesIO
import shutil
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from models.enums import TaskStatus
from models.sqlalchemy_models import TaskQueue
from services.processing_artifacts import ProcessingArtifactService
from services.task_queue import TaskQueueService


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc).replace(tzinfo=None)


def _settings(extracted_dir):
    return SimpleNamespace(EXTRACTED_DATA_DIR=str(extracted_dir))


def _execute_result(value=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _claimed_task() -> TaskQueue:
    return TaskQueue(
        id="task-1",
        task_type="process",
        folder_uuid="folder-documents",
        relative_path="invoice.pdf",
        status=TaskStatus.CLAIMED,
        task_secret="secret-1",
        content_item_id="a1b2c3",
        retry_count=0,
        max_retries=3,
        created_at=_utc(2026, 5, 9, 10),
        updated_at=_utc(2026, 5, 9, 10),
    )


def test_processing_artifacts_promote_staged_output_and_parse_document_json(tmp_path):
    service = ProcessingArtifactService(tmp_path / "extracted")
    staging = service.staging_dir("task-1")
    staging.mkdir(parents=True)
    (staging / "document.json").write_text('{"texts":[]}', encoding="utf-8")
    (staging / "pages").mkdir()
    (staging / "pages" / "page-1.png").write_bytes(b"new")

    canonical = service.canonical_dir("a1b2c3")
    canonical.mkdir(parents=True)
    (canonical / "old.txt").write_text("old", encoding="utf-8")

    document_json = service.promote_staged_output(
        task_id="task-1",
        content_item_id="a1b2c3",
    )

    assert document_json == {"texts": []}
    assert not staging.exists()
    assert not (canonical / "old.txt").exists()
    assert (canonical / "pages" / "page-1.png").read_bytes() == b"new"


def test_processing_artifacts_reject_path_traversal(tmp_path):
    service = ProcessingArtifactService(tmp_path / "extracted")

    with pytest.raises(HTTPException) as staging_exc:
        service.staging_dir("../outside")
    with pytest.raises(HTTPException) as canonical_exc:
        service.canonical_dir("../outside")

    assert staging_exc.value.status_code == 403
    assert canonical_exc.value.status_code == 403


@pytest.mark.asyncio
async def test_processing_artifacts_removes_partial_upload_when_too_large(tmp_path):
    service = ProcessingArtifactService(tmp_path / "extracted")
    upload = UploadFile(
        filename="document.json",
        file=BytesIO(b'{"texts":[]}' * 2),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.write_upload(
            task_id="task-1",
            sub_path="document.json",
            upload=upload,
            max_file_size=5,
        )

    assert exc_info.value.status_code == 413
    assert not (service.staging_dir("task-1") / "document.json").exists()


def test_processing_artifacts_reject_invalid_document_json_without_replacing_old_output(
    tmp_path,
):
    service = ProcessingArtifactService(tmp_path / "extracted")
    staging = service.staging_dir("task-1")
    staging.mkdir(parents=True)
    (staging / "document.json").write_text("{bad", encoding="utf-8")

    canonical = service.canonical_dir("a1b2c3")
    canonical.mkdir(parents=True)
    (canonical / "old.txt").write_text("old", encoding="utf-8")

    with pytest.raises(HTTPException) as exc_info:
        service.promote_staged_output(task_id="task-1", content_item_id="a1b2c3")

    assert exc_info.value.status_code == 400
    assert (canonical / "old.txt").read_text(encoding="utf-8") == "old"
    assert staging.exists()


def test_processing_artifacts_restores_previous_output_when_promotion_fails(tmp_path):
    service = ProcessingArtifactService(tmp_path / "extracted")
    staging = service.staging_dir("task-1")
    staging.mkdir(parents=True)
    (staging / "document.json").write_text('{"texts":[]}', encoding="utf-8")
    (staging / "new.txt").write_text("new", encoding="utf-8")

    canonical = service.canonical_dir("a1b2c3")
    canonical.mkdir(parents=True)
    (canonical / "old.txt").write_text("old", encoding="utf-8")

    real_move = shutil.move

    def fail_final_promotion(src, dst, *args, **kwargs):
        if src.endswith(".promote-a1b2c3-task-1") and dst.endswith("a1b2c3"):
            raise OSError("promotion failed")
        return real_move(src, dst, *args, **kwargs)

    with patch(
        "services.processing_artifacts.shutil.move",
        side_effect=fail_final_promotion,
    ):
        with pytest.raises(OSError, match="promotion failed"):
            service.promote_staged_output(task_id="task-1", content_item_id="a1b2c3")

    assert (canonical / "old.txt").read_text(encoding="utf-8") == "old"
    assert not (canonical / "new.txt").exists()
    assert not (tmp_path / "extracted" / ".promote-a1b2c3-task-1").exists()
    assert not (tmp_path / "extracted" / ".previous-a1b2c3-task-1").exists()


@pytest.mark.asyncio
async def test_complete_task_promotes_staged_output_and_persists_document_json(
    tmp_path,
):
    db = AsyncMock()
    db.add = MagicMock()
    db.execute.return_value = _execute_result(None)
    svc = TaskQueueService(db)
    task = _claimed_task()
    artifact_service = ProcessingArtifactService(tmp_path / "extracted")
    staging = artifact_service.staging_dir(task.id)
    staging.mkdir(parents=True)
    (staging / "document.json").write_text(
        '{"texts":[{"text":"ok"}]}',
        encoding="utf-8",
    )

    update_indexed = AsyncMock()
    with (
        patch(
            "services.task_queue.artifacts.get_settings",
            return_value=_settings(tmp_path / "extracted"),
        ),
        patch.object(
            TaskQueueService,
            "_get_authorized_task",
            new=AsyncMock(return_value=task),
        ),
        patch.object(
            TaskQueueService,
            "_processing_duration_ms",
            new=AsyncMock(return_value=123),
        ),
        patch.object(
            TaskQueueService,
            "_update_indexed_content_item",
            new=update_indexed,
        ),
        patch.object(TaskQueueService, "_append_task_audit_event", new=AsyncMock()),
        patch.object(TaskQueueService, "_enqueue_task_event", new=AsyncMock()),
    ):
        ok = await svc.complete_task("task-1", "secret-1")

    assert ok is True
    assert task.status == TaskStatus.COMPLETED
    assert update_indexed.await_args.args[0] == "a1b2c3"
    assert update_indexed.await_args.kwargs["document_json"] == {
        "texts": [{"text": "ok"}]
    }
    assert (artifact_service.canonical_dir("a1b2c3") / "document.json").exists()
    assert not staging.exists()


@pytest.mark.asyncio
async def test_complete_task_does_not_promote_when_newer_task_is_active(tmp_path):
    db = AsyncMock()
    db.add = MagicMock()
    db.execute.return_value = _execute_result("new-task")
    svc = TaskQueueService(db)
    task = _claimed_task()
    artifact_service = ProcessingArtifactService(tmp_path / "extracted")
    staging = artifact_service.staging_dir(task.id)
    staging.mkdir(parents=True)
    (staging / "document.json").write_text('{"texts":[]}', encoding="utf-8")
    canonical = artifact_service.canonical_dir("a1b2c3")
    canonical.mkdir(parents=True)
    (canonical / "old.txt").write_text("old", encoding="utf-8")

    update_indexed = AsyncMock()
    with (
        patch(
            "services.task_queue.artifacts.get_settings",
            return_value=_settings(tmp_path / "extracted"),
        ),
        patch.object(
            TaskQueueService,
            "_get_authorized_task",
            new=AsyncMock(return_value=task),
        ),
        patch.object(
            TaskQueueService,
            "_update_indexed_content_item",
            new=update_indexed,
        ),
    ):
        ok = await svc.complete_task("task-1", "secret-1")

    assert ok is False
    assert task.status == TaskStatus.SUPERSEDED
    update_indexed.assert_not_awaited()
    assert (canonical / "old.txt").read_text(encoding="utf-8") == "old"
    assert not staging.exists()


@pytest.mark.asyncio
async def test_retryable_failure_removes_staged_output(tmp_path):
    db = AsyncMock()
    db.add = MagicMock()
    svc = TaskQueueService(db)
    task = _claimed_task()
    artifact_service = ProcessingArtifactService(tmp_path / "extracted")
    staging = artifact_service.staging_dir(task.id)
    staging.mkdir(parents=True)
    (staging / "document.json").write_text('{"texts":[]}', encoding="utf-8")

    with (
        patch(
            "services.task_queue.artifacts.get_settings",
            return_value=_settings(tmp_path / "extracted"),
        ),
        patch.object(
            TaskQueueService,
            "_get_authorized_task",
            new=AsyncMock(return_value=task),
        ),
        patch.object(TaskQueueService, "_update_process_content_item", new=AsyncMock()),
        patch.object(TaskQueueService, "_append_task_audit_event", new=AsyncMock()),
    ):
        result = await svc.fail_task("task-1", "secret-1", "temporary")

    assert result is not None
    assert result.requeued is True
    assert not staging.exists()
