"""Watcher runtime helpers for initial scans."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterable, Iterable
from pathlib import Path

from config import BaseDataConnector, LocalFsDataConnector
from database import AsyncSessionLocal
from rls import internal_context, rls_session
from services.adapters.base import ContentEntry
from services.content.indexed_content_item import upsert_directory_entry
from services.content.sync import ObservedContentItem, sync_observed_file
from services.task_queue import TaskQueueService
from services.utils import compute_content_item_id
from .shared import (
    SourceSyncContext,
    _get_effective_viewers,
    _get_indexed_content_item,
    _upsert_directory_from_entry,
)

logger = logging.getLogger(__name__)


async def _scan_entry(
    source: SourceSyncContext,
    entry: ContentEntry,
) -> tuple[int, int]:
    relative_path = entry.relative_path

    if entry.is_dir:
        await _upsert_directory_from_entry(
            source.db,
            source.folder,
            relative_path,
            entry.is_symlink,
            source.viewers,
        )
        return 0, 0

    if not entry.is_file:
        return 0, 0

    return await _scan_file_entry(source, entry, relative_path)


async def _scan_file_entry(
    source: SourceSyncContext,
    entry: ContentEntry,
    relative_path: str,
) -> tuple[int, int]:
    content_item_id = compute_content_item_id(source.folder.uuid, relative_path)
    record = await _get_indexed_content_item(source.db, content_item_id)
    sync_result = await sync_observed_file(
        db=source.db,
        task_svc=source.task_svc,
        folder=source.folder,
        observed_file=ObservedContentItem.from_entry(source.folder.uuid, entry),
        record=record,
        viewers=source.viewers,
    )
    if not sync_result.changed:
        return 0, 1
    if sync_result.metadata_changed and not sync_result.enqueued:
        logger.debug("Synced metadata for %s", relative_path)
    return (1 if sync_result.enqueued else 0), 0


async def _iter_entries_recursive(
    folder: BaseDataConnector,
) -> AsyncIterable[ContentEntry]:
    adapter = folder.get_adapter()

    async def _walk(prefix: str):
        try:
            entries = await adapter.list_directory(prefix)
        except Exception:
            logger.warning("Failed to list %s/%s", folder.name, prefix, exc_info=True)
            return
        for entry in entries:
            if entry.name.startswith("."):
                continue
            yield entry
            if entry.is_dir:
                async for child in _walk(entry.relative_path):
                    yield child

    async for entry in _walk(""):
        yield entry


async def _scan_existing(folder: BaseDataConnector) -> None:
    if isinstance(folder, LocalFsDataConnector):
        data_path = Path(folder.path)
        if not data_path.exists():
            return

    logger.info("Scanning %s", folder.name)
    count, skipped = await _scan_existing_entries(
        folder,
        _iter_entries_recursive(folder),
    )

    logger.info("Queued %d files (%d skipped) from %s", count, skipped, folder.name)


async def _scan_existing_entries(
    folder: BaseDataConnector,
    entries: AsyncIterable[ContentEntry] | Iterable[ContentEntry],
) -> tuple[int, int]:
    count = 0
    skipped = 0

    async with rls_session(AsyncSessionLocal, internal_context("watcher")) as db:
        svc = TaskQueueService(db)
        viewers = await _get_effective_viewers(db, folder.uuid)
        source = SourceSyncContext(db=db, task_svc=svc, folder=folder, viewers=viewers)

        await upsert_directory_entry(
            db,
            compute_content_item_id(folder.uuid, ""),
            folder.uuid,
            "",
            allowed_viewers=viewers.allowed_or_none,
            denied_viewers=viewers.denied_or_none,
            auto_commit=False,
        )

        async for entry in _iter_scan_entries(entries):
            queued_inc, skipped_inc = await _scan_entry(source, entry)
            count += queued_inc
            skipped += skipped_inc

        await db.commit()

    return count, skipped


async def _iter_scan_entries(
    entries: AsyncIterable[ContentEntry] | Iterable[ContentEntry],
) -> AsyncIterable[ContentEntry]:
    if hasattr(entries, "__aiter__"):
        async for entry in entries:
            yield entry
        return

    for entry in entries:
        yield entry
