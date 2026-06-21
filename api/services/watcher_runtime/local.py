"""Watcher runtime helpers for local filesystem and SMB watch events."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from watchfiles import Change, awatch

from config import LocalFsDataConnector
from database import AsyncSessionLocal
from rls import internal_context, rls_session
from services.content.deletion import ContentDeletionService
from services.content.sync import (
    ContentSyncResult,
    ObservedContentItem,
    sync_observed_file,
    upsert_directory_record,
)
from services.smb_watcher import SmbNotifyWatcher
from services.task_queue import TaskQueueService
from services.utils import compute_content_item_id, get_content_item_metadata
from .scan import _scan_existing
from .shared import (
    LocalEventContext,
    _get_effective_viewers,
    _get_indexed_content_item,
    _safe_relative_path,
)

logger = logging.getLogger(__name__)


async def _handle_file_deleted(
    db: AsyncSession,
    folder: LocalFsDataConnector,
    content_item_id: str,
    relative_path: str,
    *,
    delete_service_factory=ContentDeletionService,
) -> None:
    await delete_service_factory(db).delete_content_path(
        folder_uuid=folder.uuid,
        relative_path=relative_path,
        content_item_id=content_item_id,
        source="watcher",
        metadata={"origin": "local_watcher"},
    )
    logger.info("File event: delete %s", relative_path)


async def _handle_directory_change(
    change_type: Change,
    path_obj: Path,
    event: LocalEventContext,
    *,
    get_indexed_content_item_fn=_get_indexed_content_item,
    get_effective_viewers_fn=_get_effective_viewers,
    delete_service_factory=ContentDeletionService,
) -> bool:
    record = await get_indexed_content_item_fn(event.db, event.content_item_id)

    if path_obj.is_dir():
        viewers = await get_effective_viewers_fn(event.db, event.folder.uuid)
        await upsert_directory_record(
            event.db,
            event.folder,
            event.relative_path,
            path_obj.is_symlink(),
            viewers,
        )
        logger.debug("Directory indexed: %s", event.relative_path)
        return True

    if record and record.is_dir and change_type == Change.deleted:
        await delete_service_factory(event.db).delete_content_path(
            folder_uuid=event.folder.uuid,
            relative_path=event.relative_path,
            content_item_id=event.content_item_id,
            source="watcher",
            metadata={"origin": "local_watcher"},
        )
        logger.info("Directory deleted (cascaded): %s", event.relative_path)
        return True

    return change_type != Change.deleted


async def _handle_local_sync_result(
    sync_result: ContentSyncResult,
    event: LocalEventContext,
) -> None:
    if not sync_result.changed and not sync_result.enqueued:
        logger.debug("Skipping unchanged file: %s", event.relative_path)
        return

    if sync_result.enqueued:
        logger.info("File content change: process %s", event.relative_path)
    elif sync_result.content_changed and not event.folder.auto_process_new:
        logger.debug(
            "File content changed but auto_process_new=False, skipping: %s",
            event.relative_path,
        )
    elif sync_result.content_changed:
        logger.warning(
            "File content change detected but processing was not enqueued: %s",
            event.relative_path,
        )
    elif sync_result.metadata_changed:
        logger.info("File metadata change: synced %s", event.relative_path)


async def _handle_file_added_or_modified(
    path_obj: Path,
    event: LocalEventContext,
    *,
    get_effective_viewers_fn=_get_effective_viewers,
    get_indexed_content_item_fn=_get_indexed_content_item,
) -> None:
    viewers = await get_effective_viewers_fn(event.db, event.folder.uuid)
    metadata = get_content_item_metadata(path_obj)
    record = await get_indexed_content_item_fn(event.db, event.content_item_id)
    sync_result = await sync_observed_file(
        db=event.db,
        task_svc=event.task_svc,
        folder=event.folder,
        observed_file=ObservedContentItem.from_metadata(
            event.folder.uuid,
            event.relative_path,
            metadata,
        ),
        record=record,
        viewers=viewers,
    )
    await _handle_local_sync_result(sync_result, event)


async def _handle_change(
    change_type: Change,
    path_str: str,
    folder: LocalFsDataConnector,
    svc: TaskQueueService,
    db: AsyncSession,
) -> None:
    path_obj = Path(path_str)

    if path_obj.name.startswith("."):
        return

    relative_path = _safe_relative_path(path_obj, folder)
    if relative_path is None:
        return
    event = LocalEventContext(
        db=db,
        task_svc=svc,
        folder=folder,
        content_item_id=compute_content_item_id(folder.uuid, relative_path),
        relative_path=relative_path,
    )

    if path_obj.is_dir() or (change_type == Change.deleted and not path_obj.exists()):
        handled = await _handle_directory_change(change_type, path_obj, event)
        if handled:
            return

    if change_type == Change.deleted:
        await _handle_file_deleted(
            db,
            folder,
            event.content_item_id,
            event.relative_path,
        )
    else:
        await _handle_file_added_or_modified(path_obj, event)


async def _watch_folder(folder: LocalFsDataConnector) -> None:
    logger.info("Watching %s at %s", folder.name, folder.path)
    poll_delay_ms = max(1, int(folder.poll_interval_seconds)) * 1000

    while True:
        try:
            async for changes in awatch(
                folder.path,
                recursive=True,
                force_polling=folder.force_polling,
                poll_delay_ms=poll_delay_ms,
            ):
                await _apply_change_batch(folder, changes)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Watcher loop crashed for %s (%s), retrying in %ss",
                folder.name,
                folder.path,
                folder.poll_interval_seconds,
            )
            await asyncio.sleep(max(1, int(folder.poll_interval_seconds)))


async def _watch_folder_smb(folder: LocalFsDataConnector) -> None:
    logger.info("Watching %s via SMB CHANGE_NOTIFY at %s", folder.name, folder.path)
    watcher = SmbNotifyWatcher(folder)
    async for batch in watcher.watch():
        if not batch:
            await _scan_existing(folder)
            continue
        await _apply_change_batch(folder, batch)


async def _apply_change_batch(
    folder: LocalFsDataConnector,
    changes: Iterable[tuple[Change, str]],
) -> None:
    async with rls_session(AsyncSessionLocal, internal_context("watcher")) as db:
        svc = TaskQueueService(db)
        for change_type, path_str in changes:
            await _handle_change(change_type, path_str, folder, svc, db)
        await db.commit()
