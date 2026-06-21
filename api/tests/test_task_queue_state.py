"""Tests for pure task queue state helpers."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.task_queue import ProcessTaskMetadata
from models.sqlalchemy_models import IndexedContentItem, TaskQueue
from services.task_queue.access_ops import (
    TaskQueueAccessOperations,
    task_metadata_payload,
)
from services.task_queue.process_state_ops import indexed_content_item_exists
from services.task_queue.state import (
    is_retryable_failure,
    mark_task_completed,
    mark_task_requeued,
    new_queued_indexed_content_item,
    processing_completed_update_values,
    processing_retry_update_values,
    relative_path_parts,
)


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc).replace(tzinfo=None)


def test_relative_path_parts_normalizes_parent_name_and_extension():
    parent_path, name, extension = relative_path_parts("nested/Invoice.PDF")

    assert parent_path == "nested"
    assert name == "Invoice.PDF"
    assert extension == ".pdf"


def test_new_queued_indexed_content_item_preserves_metadata_and_visibility_flags():
    metadata = ProcessTaskMetadata(
        content_item_id="file-1",
        modified_time=10.0,
        created_time=9.0,
        size_bytes=42,
        is_symlink=True,
        allowed_viewers=["user:a"],
        denied_viewers=["user:b"],
        processing_config={"ocr": True},
    )

    record = new_queued_indexed_content_item(
        content_item_id="file-1",
        folder_uuid="folder-1",
        relative_path=".hidden/report.pdf",
        metadata=metadata,
        task_id="task-1",
        task_secret="secret-1",
    )

    assert isinstance(record, IndexedContentItem)
    assert record.parent_path == ".hidden"
    assert record.name == "report.pdf"
    assert record.extension == ".pdf"
    assert record.is_hidden is False
    assert record.is_symlink is True
    assert record.allowed_viewers == ["user:a"]
    assert record.denied_viewers == ["user:b"]
    assert record.last_processing_config == {"ocr": True}


def test_mark_task_requeued_resets_claim_fields_and_increments_retry_count():
    task = TaskQueue(
        id="task-1",
        task_type="process",
        status="CLAIMED",
        task_secret="old-secret",
        retry_count=1,
        max_retries=3,
        claimed_by="worker-1",
        claimed_at=_utc(2026, 4, 26, 9),
        updated_at=_utc(2026, 4, 26, 9),
    )

    mark_task_requeued(
        task,
        now=_utc(2026, 4, 26, 10),
        new_secret="new-secret",
        error_message="temporary failure",
    )

    assert task.status == "PENDING"
    assert task.claimed_by is None
    assert task.claimed_at is None
    assert task.task_secret == "new-secret"
    assert task.retry_count == 2
    assert task.error_message == "temporary failure"


def test_mark_task_completed_clears_secret_and_stale_error():
    task = TaskQueue(
        id="task-1",
        task_type="process",
        status="CLAIMED",
        task_secret="old-secret",
        error_message="previous retry failed",
        stage="chunking",
        updated_at=_utc(2026, 4, 26, 9),
    )

    mark_task_completed(task, now=_utc(2026, 4, 26, 10))

    assert task.status == "COMPLETED"
    assert task.task_secret is None
    assert task.error_message is None
    assert task.stage is None
    assert task.stage_updated_at == _utc(2026, 4, 26, 10)
    assert task.updated_at == _utc(2026, 4, 26, 10)


def test_processing_completed_update_values_clear_processing_stage():
    values = processing_completed_update_values(
        now=_utc(2026, 4, 26, 10), duration_ms=1234
    )

    assert values["processing_status"].value == "COMPLETED"
    assert values["processing_stage"] is None


def test_is_retryable_failure_requires_retries_remaining_and_nonfatal_errors():
    task = TaskQueue(id="task-1", task_type="process", retry_count=1, max_retries=2)

    assert is_retryable_failure(task, fatal_failure=False) is True
    assert is_retryable_failure(task, fatal_failure=True) is False

    task.retry_count = 2
    assert is_retryable_failure(task, fatal_failure=False) is False


def test_processing_retry_update_values_clear_runtime_fields_and_keep_new_secret():
    values = processing_retry_update_values(
        error_message="temporary failure",
        new_secret="new-secret",
    )

    assert values["task_secret"] == "new-secret"
    assert values["error_message"] == "temporary failure"
    assert values["processing_started_at"] is None
    assert values["processing_duration_ms"] is None


def test_processing_completed_update_values_only_include_optional_payloads_when_present():
    values = processing_completed_update_values(
        now=_utc(2026, 4, 26, 10),
        duration_ms=321,
    )

    assert values["processing_duration_ms"] == 321
    assert "last_processing_config" not in values


def test_task_metadata_payload_parses_dict_and_optional_content_item_id():
    task = TaskQueue(
        id="task-1",
        task_type="process",
        content_item_id="file-1",
        metadata_json='{"source_name":"documents"}',
    )

    assert task_metadata_payload(task) == {
        "source_name": "documents",
        "content_item_id": "file-1",
    }
    assert task_metadata_payload(task, include_content_item_id=False) == {
        "source_name": "documents"
    }


def test_task_metadata_payload_defaults_non_object_json_to_empty_payload():
    task = TaskQueue(
        id="task-1",
        task_type="process",
        metadata_json='["not", "an", "object"]',
    )

    assert task_metadata_payload(task) == {}


def test_task_metadata_payload_defaults_invalid_json_to_empty_payload():
    task = TaskQueue(
        id="task-1",
        task_type="process",
        metadata_json="{not-json",
    )

    assert task_metadata_payload(task) == {}


def test_training_task_metadata_returns_none_for_invalid_payload():
    task = TaskQueue(
        id="task-1",
        task_type="train_content_enrichment_model",
        metadata_json='{"training_job_id":"job-1"}',
    )

    assert TaskQueueAccessOperations.training_task_metadata(task) is None


@pytest.mark.asyncio
async def test_indexed_content_item_exists_returns_presence():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = "file-1"
    db.execute.return_value = result

    assert await indexed_content_item_exists(db, "file-1") is True

    result.scalar_one_or_none.return_value = None

    assert await indexed_content_item_exists(db, "file-1") is False
