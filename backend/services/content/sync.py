"""Shared file-sync helpers used by watcher and reconciliation paths."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from config import BaseDataConnector
from models.enums import ProcessingStatus
from models.task_queue import EnqueueProcessTask, ProcessTaskMetadata
from models.sqlalchemy_models import IndexedContentItem
from services.adapters.base import ContentEntry
from services.task_queue import TaskQueueService
from services.utils import compute_content_item_id

from .indexed_content_item import upsert_directory_entry, upsert_indexed_content_item
from .indexing import (
    determine_processing_status,
    has_content_changed,
    has_metadata_changed,
)
from .metadata import metadata_float, metadata_int

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EffectiveViewers:
    allowed: list[str]
    denied: list[str]
    allowed_or_none: list[str] | None
    denied_or_none: list[str] | None


@dataclass(frozen=True)
class ObservedContentItem:
    content_item_id: str
    relative_path: str
    modified_time: float
    change_time: float
    size_bytes: int
    is_symlink: bool
    file_extension: str | None

    @classmethod
    def from_entry(cls, folder_uuid: str, entry: ContentEntry) -> "ObservedContentItem":
        return cls(
            content_item_id=compute_content_item_id(folder_uuid, entry.relative_path),
            relative_path=entry.relative_path,
            modified_time=entry.modified_time,
            change_time=entry.change_time,
            size_bytes=entry.size_bytes,
            is_symlink=entry.is_symlink,
            file_extension=Path(entry.name).suffix.lower() or None,
        )

    @classmethod
    def from_metadata(
        cls,
        folder_uuid: str,
        relative_path: str,
        metadata: dict[str, object],
    ) -> "ObservedContentItem":
        return cls(
            content_item_id=compute_content_item_id(folder_uuid, relative_path),
            relative_path=relative_path,
            modified_time=metadata_float(metadata, "modified_time"),
            change_time=metadata_float(metadata, "created_time"),
            size_bytes=metadata_int(metadata, "size_bytes"),
            is_symlink=bool(metadata.get("is_symlink", False)),
            file_extension=Path(relative_path).suffix.lower() or None,
        )


@dataclass(frozen=True)
class ContentSyncResult:
    metadata_changed: bool
    content_changed: bool
    enqueued: bool = False

    @property
    def changed(self) -> bool:
        return self.metadata_changed or self.content_changed


def build_effective_viewers(
    allowed_viewers: list[str],
    denied_viewers: list[str],
) -> EffectiveViewers:
    return EffectiveViewers(
        allowed=allowed_viewers,
        denied=denied_viewers,
        allowed_or_none=allowed_viewers or None,
        denied_or_none=denied_viewers or None,
    )


def build_task_metadata(
    observed_file: ObservedContentItem,
    viewers: EffectiveViewers,
) -> ProcessTaskMetadata:
    return ProcessTaskMetadata(
        content_item_id=observed_file.content_item_id,
        size_bytes=observed_file.size_bytes,
        modified_time=observed_file.modified_time,
        created_time=observed_file.change_time,
        is_symlink=observed_file.is_symlink,
        file_extension=observed_file.file_extension,
        allowed_viewers=viewers.allowed,
        denied_viewers=viewers.denied,
    )


async def upsert_directory_record(
    db,
    folder: BaseDataConnector,
    relative_path: str,
    is_symlink: bool,
    viewers: EffectiveViewers,
) -> None:
    await upsert_directory_entry(
        db,
        compute_content_item_id(folder.uuid, relative_path),
        folder.uuid,
        relative_path,
        allowed_viewers=viewers.allowed_or_none,
        denied_viewers=viewers.denied_or_none,
        is_symlink=is_symlink,
        auto_commit=False,
    )


def should_enqueue_processing(
    record: IndexedContentItem | None,
    folder: BaseDataConnector,
    *,
    content_changed: bool,
    requeue_if_status_queued: bool = False,
) -> bool:
    return bool(
        folder.auto_process_new
        and (
            content_changed
            or (
                requeue_if_status_queued
                and record is not None
                and record.processing_status == ProcessingStatus.QUEUED
            )
        )
    )


async def sync_observed_file(
    *,
    db,
    task_svc: TaskQueueService,
    folder: BaseDataConnector,
    observed_file: ObservedContentItem,
    record: IndexedContentItem | None,
    viewers: EffectiveViewers,
    requeue_if_status_queued: bool = False,
) -> ContentSyncResult:
    metadata_changed = has_metadata_changed(record, observed_file.change_time)
    content_changed = has_content_changed(
        record, observed_file.modified_time, observed_file.size_bytes
    )
    enqueue_processing = should_enqueue_processing(
        record,
        folder,
        content_changed=content_changed,
        requeue_if_status_queued=requeue_if_status_queued,
    )

    if not metadata_changed and not content_changed and not enqueue_processing:
        return ContentSyncResult(False, False, False)

    if metadata_changed or content_changed:
        await upsert_indexed_content_item(
            db,
            observed_file.content_item_id,
            folder.uuid,
            observed_file.relative_path,
            modified_time=observed_file.modified_time,
            change_time=observed_file.change_time,
            size_bytes=observed_file.size_bytes,
            allowed_viewers=viewers.allowed_or_none,
            denied_viewers=viewers.denied_or_none,
            status=determine_processing_status(record, folder),
            is_symlink=observed_file.is_symlink,
            auto_commit=False,
        )

    enqueued = False
    if enqueue_processing:
        try:
            await task_svc.enqueue_process(
                EnqueueProcessTask(
                    content_item_id=observed_file.content_item_id,
                    folder_uuid=folder.uuid,
                    relative_path=observed_file.relative_path,
                    metadata=build_task_metadata(observed_file, viewers),
                ),
                auto_commit=False,
            )
            enqueued = True
        except Exception:
            logger.exception(
                "Failed to enqueue processing for %s/%s",
                folder.name,
                observed_file.relative_path,
            )

    return ContentSyncResult(
        metadata_changed=metadata_changed,
        content_changed=content_changed,
        enqueued=enqueued,
    )
