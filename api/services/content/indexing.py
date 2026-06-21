"""Shared file-indexing helpers used by watcher and reconcile."""

from models.enums import ProcessingStatus
from models.sqlalchemy_models import IndexedContentItem
from config import BaseDataConnector


def has_content_changed(
    record: IndexedContentItem | None,
    mtime: float,
    size: int,
) -> bool:
    """Return True when the file content has changed vs. the DB record."""
    return not record or record.modified_time != mtime or record.size_bytes != size


def has_metadata_changed(
    record: IndexedContentItem | None,
    ctime: float,
) -> bool:
    """Return True when metadata (ctime) differs."""
    return not record or record.change_time != ctime


def determine_processing_status(
    record: IndexedContentItem | None,
    folder: BaseDataConnector,
) -> str | None:
    """Decide the processing_status to write when upserting a file record.

    Rules:
    - If the record exists, preserve its current status (e.g. COMPLETED).
    - For new files, set QUEUED when the folder has processing enabled, else None.
    - Callers that enqueue a task override to QUEUED via TaskQueueService.
    """
    if record:
        return record.processing_status
    return ProcessingStatus.QUEUED if folder.auto_process_new else None
