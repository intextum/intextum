"""Pure task and indexed-file transition helpers for the task queue."""

from __future__ import annotations

import os
import mimetypes
from datetime import datetime
from typing import Any

from models.enums import ProcessingStatus, TaskStatus
from models.task_queue import ProcessTaskMetadata
from models.sqlalchemy_models import IndexedContentItem, TaskQueue


def relative_path_parts(relative_path: str) -> tuple[str, str, str | None]:
    """Split a relative path into parent path, basename, and lowercase extension."""
    parent_path = os.path.dirname(relative_path)
    name = os.path.basename(relative_path)
    _, ext = os.path.splitext(name)
    return parent_path, name, ext.lower() if ext else None


def queued_content_item_update_values(
    *,
    folder_uuid: str,
    relative_path: str,
    metadata: ProcessTaskMetadata,
    task_id: str,
    task_secret: str,
) -> dict[str, Any]:
    """Build the standard IndexedContentItem values for a queued process task."""
    return {
        "folder_uuid": folder_uuid,
        "relative_path": relative_path,
        "modified_time": metadata.modified_time,
        "size_bytes": metadata.size_bytes,
        "processing_status": ProcessingStatus.QUEUED,
        "task_id": task_id,
        "task_secret": task_secret,
        "error_message": None,
    }


def apply_indexed_content_item_updates(
    record: IndexedContentItem, **values: Any
) -> None:
    """Mutate an IndexedContentItem in place using the supplied field values."""
    for key, value in values.items():
        setattr(record, key, value)


def new_queued_indexed_content_item(
    *,
    content_item_id: str,
    folder_uuid: str,
    relative_path: str,
    metadata: ProcessTaskMetadata,
    task_id: str,
    task_secret: str,
) -> IndexedContentItem:
    """Create a new IndexedContentItem row seeded from a queued process task."""
    parent_path, name, extension = relative_path_parts(relative_path)
    return IndexedContentItem(
        content_item_id=content_item_id,
        folder_uuid=folder_uuid,
        content_kind="file",
        relative_path=relative_path,
        modified_time=metadata.modified_time,
        change_time=metadata.created_time,
        size_bytes=metadata.size_bytes,
        processing_status=ProcessingStatus.QUEUED,
        task_id=task_id,
        task_secret=task_secret,
        parent_path=parent_path,
        name=name,
        display_name=name,
        extension=extension,
        mime_type=mimetypes.guess_type(relative_path)[0],
        is_container=False,
        is_hidden=name.startswith("."),
        is_symlink=metadata.is_symlink,
        allowed_viewers=metadata.allowed_viewers,
        denied_viewers=metadata.denied_viewers,
        last_processing_config=metadata.processing_config,
    )


def process_content_item_id(task: TaskQueue) -> str | None:
    """Return the affected file id for process tasks."""
    if task.task_type == "process":
        return task.content_item_id
    return None


def mark_task_claimed(task: TaskQueue, *, worker_id: str, now: datetime) -> None:
    """Apply in-place TaskQueue changes for a claimed task."""
    task.status = TaskStatus.CLAIMED
    task.claimed_by = worker_id
    task.claimed_at = now
    task.updated_at = now


def mark_task_requeued(
    task: TaskQueue,
    *,
    now: datetime,
    new_secret: str,
    error_message: str,
) -> None:
    """Apply in-place TaskQueue changes for a retryable failure."""
    task.status = TaskStatus.PENDING
    task.claimed_by = None
    task.claimed_at = None
    task.task_secret = new_secret
    task.retry_count += 1
    task.error_message = error_message
    task.stage = None
    task.stage_updated_at = now
    task.updated_at = now


def mark_task_failed(task: TaskQueue, *, now: datetime, error_message: str) -> None:
    """Apply in-place TaskQueue changes for a terminal failure."""
    task.status = TaskStatus.FAILED
    task.task_secret = None
    task.error_message = error_message
    task.stage = None
    task.stage_updated_at = now
    task.updated_at = now


def mark_task_completed(task: TaskQueue, *, now: datetime) -> None:
    """Apply in-place TaskQueue changes for a completed task."""
    task.status = TaskStatus.COMPLETED
    task.task_secret = None
    task.error_message = None
    task.stage = None
    task.stage_updated_at = now
    task.updated_at = now


def mark_task_superseded(task: TaskQueue, *, now: datetime, reason: str) -> None:
    """Apply in-place TaskQueue changes for a superseded task."""
    task.status = TaskStatus.SUPERSEDED
    task.task_secret = None
    task.error_message = reason
    task.stage = None
    task.stage_updated_at = now
    task.updated_at = now


def is_retryable_failure(task: TaskQueue, *, fatal_failure: bool) -> bool:
    """Return whether the current task failure should be retried."""
    return (not fatal_failure) and task.retry_count < task.max_retries


def processing_claim_update_values(*, worker_id: str, now: datetime) -> dict[str, Any]:
    """Build IndexedContentItem update values for a claimed task entering processing."""
    return {
        "processing_status": ProcessingStatus.PROCESSING,
        "processing_started_at": now,
        "processed_by": worker_id,
        "processed_at": None,
        "processing_duration_ms": None,
    }


def processing_retry_update_values(
    *, error_message: str, new_secret: str
) -> dict[str, Any]:
    """Build IndexedContentItem update values for a re-queued processing failure."""
    return {
        "processing_status": ProcessingStatus.RETRYING,
        "processing_stage": None,
        "error_message": error_message,
        "task_secret": new_secret,
        "processing_started_at": None,
        "processing_duration_ms": None,
    }


def processing_failed_update_values(*, error_message: str) -> dict[str, Any]:
    """Build IndexedContentItem update values for a terminal task failure."""
    return {
        "processing_status": ProcessingStatus.FAILED,
        "processing_stage": None,
        "error_message": error_message,
        "task_secret": None,
    }


def processing_revoked_update_values(*, reason: str) -> dict[str, Any]:
    """Build IndexedContentItem update values for an aborted or superseded task."""
    return {
        "processing_status": ProcessingStatus.REVOKED,
        "processing_stage": None,
        "error_message": reason,
        "task_secret": None,
    }


def processing_completed_update_values(
    *,
    now: datetime,
    duration_ms: int | None,
    processing_config: dict[str, object] | None = None,
) -> dict[str, object | None]:
    """Build IndexedContentItem update values for a completed processing task."""
    update_values: dict[str, object | None] = {
        "processing_status": ProcessingStatus.COMPLETED,
        "processing_stage": None,
        "indexed_at": now,
        "processed_at": now,
        "processing_duration_ms": duration_ms,
        "error_message": None,
        "task_secret": None,
    }
    if processing_config is not None:
        update_values["last_processing_config"] = processing_config
    return update_values
