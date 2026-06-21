"""Watcher runtime helpers for remote polling sources."""

from __future__ import annotations

import asyncio
import logging

from config import BaseDataConnector
from database import AsyncSessionLocal
from rls import internal_context, rls_session
from models.sqlalchemy_models import IndexedContentItem
from services.adapters.base import ContentEntry
from services.content.deletion import ContentDeletionService
from services.content.sync import ObservedContentItem, sync_observed_file
from services.task_queue import TaskQueueService
from .shared import (
    SourceSyncContext,
    _get_effective_viewers,
    _load_folder_records,
    _upsert_directory_from_entry,
    _visible_entries_by_path,
)

logger = logging.getLogger(__name__)


async def _sync_s3_entry(
    source: SourceSyncContext,
    rel_path: str,
    entry: ContentEntry,
    db_records: dict[str, IndexedContentItem],
) -> bool:
    record = db_records.get(rel_path)

    if entry.is_dir:
        if rel_path in db_records:
            return False
        await _upsert_directory_from_entry(
            source.db,
            source.folder,
            rel_path,
            entry.is_symlink,
            source.viewers,
        )
        return True

    if not entry.is_file:
        return False

    sync_result = await sync_observed_file(
        db=source.db,
        task_svc=source.task_svc,
        folder=source.folder,
        observed_file=ObservedContentItem.from_entry(source.folder.uuid, entry),
        record=record,
        viewers=source.viewers,
    )
    return sync_result.changed


async def _sync_s3_current_paths(
    source: SourceSyncContext,
    current_paths: dict[str, ContentEntry],
    db_records: dict[str, IndexedContentItem],
) -> bool:
    changed = False

    for rel_path, entry in current_paths.items():
        if await _sync_s3_entry(source, rel_path, entry, db_records):
            changed = True

    return changed


async def _remove_s3_missing_records(
    db,
    folder: BaseDataConnector,
    db_records: dict[str, IndexedContentItem],
    current_paths: dict[str, ContentEntry],
    *,
    delete_service_factory=ContentDeletionService,
) -> bool:
    stale_paths = sorted(
        (
            rel_path
            for rel_path in db_records
            if rel_path and rel_path not in current_paths
        ),
        key=len,
    )
    deleted_roots: list[str] = []
    delete_svc = delete_service_factory(db)

    for rel_path in stale_paths:
        if any(rel_path.startswith(f"{root}/") for root in deleted_roots):
            continue
        await delete_svc.delete_content_path(
            folder_uuid=folder.uuid,
            relative_path=rel_path,
            source="watcher",
            metadata={"origin": "s3_poll"},
        )
        deleted_roots.append(rel_path)

    return bool(deleted_roots)


async def _run_s3_poll_cycle(
    folder: BaseDataConnector,
    current_paths: dict[str, ContentEntry],
) -> None:
    async with rls_session(AsyncSessionLocal, internal_context("watcher")) as db:
        svc = TaskQueueService(db)
        viewers = await _get_effective_viewers(db, folder.uuid)
        db_records = await _load_folder_records(db, folder.uuid)
        source = SourceSyncContext(db=db, task_svc=svc, folder=folder, viewers=viewers)

        changed = await _sync_s3_current_paths(source, current_paths, db_records)
        removed = await _remove_s3_missing_records(
            db, folder, db_records, current_paths
        )

        if changed or removed:
            await db.commit()
            logger.info("S3 poll cycle for %s: changes synced", folder.name)
        else:
            logger.debug("S3 poll cycle for %s: no changes", folder.name)


async def _collect_entries_recursive(
    folder: BaseDataConnector,
) -> list[ContentEntry]:
    adapter = folder.get_adapter()
    result: list[ContentEntry] = []

    async def _walk(prefix: str) -> None:
        try:
            entries = await adapter.list_directory(prefix)
        except Exception:
            logger.warning("Failed to list %s/%s", folder.name, prefix, exc_info=True)
            return
        for entry in entries:
            if entry.name.startswith("."):
                continue
            result.append(entry)
            if entry.is_dir:
                await _walk(entry.relative_path)

    await _walk("")
    return result


async def _watch_s3_poll(folder: BaseDataConnector) -> None:
    poll_interval = max(30, int(folder.poll_interval_seconds))
    logger.info("Watching %s via S3 polling (interval=%ds)", folder.name, poll_interval)

    while True:
        try:
            entries = await _collect_entries_recursive(folder)
            current_paths = _visible_entries_by_path(entries)
            await _run_s3_poll_cycle(folder, current_paths)

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "S3 poll cycle crashed for %s, retrying in %ds",
                folder.name,
                poll_interval,
            )

        await asyncio.sleep(poll_interval)
