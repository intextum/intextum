"""File reconciliation logic."""

import asyncio
import logging
import unicodedata
from collections.abc import Coroutine
from dataclasses import replace
from typing import Any

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from config import get_settings, BaseDataConnector
from services.content.deletion import ContentDeletionService
from services.content.indexed_content_item import upsert_directory_entry
from models.enums import ProcessingStatus, TaskStatus
from models.sqlalchemy_models import IndexedContentItem, TaskQueue
from services.permission import PermissionService
from services.task_queue import TaskQueueService
from services.utils import compute_content_item_id, utcnow
from services.adapters.base import ContentEntry
from .helpers import get_record
from .sync import (
    EffectiveViewers,
    ObservedContentItem,
    build_effective_viewers,
    sync_observed_file,
    upsert_directory_record,
)

logger = logging.getLogger(__name__)

ACTIVE_PROCESSING_STATUSES = {
    ProcessingStatus.QUEUED.value,
    ProcessingStatus.PROCESSING.value,
    ProcessingStatus.RETRYING.value,
}


def _normalize_seen_path(relative_path: str) -> str:
    return unicodedata.normalize("NFC", relative_path.strip("/"))


class Reconciler:
    """Handles reconciliation of filesystem state with the database."""

    _background_tasks: dict[tuple[str, str], asyncio.Task[Any]] = {}
    _background_task_lock: asyncio.Lock | None = None

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()
        self._permission_svc = PermissionService(db)

    @classmethod
    def _background_task_key(
        cls, folder: BaseDataConnector, folder_rel_path: str
    ) -> tuple[str, str]:
        return (folder.uuid, folder_rel_path or "")

    @classmethod
    def _background_lock(cls) -> asyncio.Lock:
        if cls._background_task_lock is None:
            cls._background_task_lock = asyncio.Lock()
        return cls._background_task_lock

    @classmethod
    def _release_background_task(
        cls,
        key: tuple[str, str],
        task: asyncio.Task[Any],
    ) -> None:
        current = cls._background_tasks.get(key)
        if current is task:
            cls._background_tasks.pop(key, None)

    @classmethod
    def _create_background_task(
        cls,
        coroutine: Coroutine[object, object, None],
    ) -> asyncio.Task[Any]:
        return asyncio.create_task(coroutine)

    async def _get_effective_viewers(self, folder_uuid: str) -> EffectiveViewers:
        allowed, denied = await self._permission_svc.compute_effective_viewers(
            folder_uuid
        )
        return build_effective_viewers(allowed, denied)

    @staticmethod
    def _parent_path(folder_rel_path: str) -> str:
        return folder_rel_path or ""

    @classmethod
    def _child_record_filters(cls, folder_uuid: str, folder_rel_path: str):
        parent_path = cls._parent_path(folder_rel_path)
        return (
            IndexedContentItem.folder_uuid == folder_uuid,
            IndexedContentItem.parent_path == parent_path,
            IndexedContentItem.relative_path != (folder_rel_path or ""),
        )

    async def _child_record_count(self, folder_uuid: str, folder_rel_path: str) -> int:
        count_stmt = select(func.count(IndexedContentItem.content_item_id)).where(
            *self._child_record_filters(folder_uuid, folder_rel_path)
        )
        return int((await self.db.execute(count_stmt)).scalar() or 0)

    async def _child_db_records(
        self, folder_uuid: str, folder_rel_path: str
    ) -> dict[str, IndexedContentItem]:
        stmt = select(IndexedContentItem).where(
            *self._child_record_filters(folder_uuid, folder_rel_path)
        )
        result = await self.db.execute(stmt)
        return {record.relative_path: record for record in result.scalars().all()}

    async def maybe_reconcile(
        self, folder: BaseDataConnector, folder_rel_path: str
    ) -> None:
        """Check if a directory needs reconciliation and trigger if needed."""
        display_path = folder_rel_path or "(root)"
        dir_id = compute_content_item_id(folder.uuid, folder_rel_path or "")
        dir_entry = await get_record(self.db, dir_id)

        now = utcnow()
        if dir_entry and dir_entry.last_scanned_at:
            age = (now - dir_entry.last_scanned_at).total_seconds()
            if age < self.settings.RECONCILE_TTL_SECONDS:
                logger.debug(
                    "Reconcile skip %s/%s: scanned %.0fs ago (TTL=%ds)",
                    folder.name,
                    display_path,
                    age,
                    self.settings.RECONCILE_TTL_SECONDS,
                )
                return

        count = await self._child_record_count(folder.uuid, folder_rel_path)

        if count == 0:
            logger.info(
                "Reconcile inline %s/%s: no DB data, blocking until done",
                folder.name,
                display_path,
            )
            await self._do_reconcile(folder, folder_rel_path)
        else:
            await self._schedule_background_reconcile(
                folder,
                folder_rel_path,
                display_path=display_path,
                stale_record_count=count,
            )

    async def _schedule_background_reconcile(
        self,
        folder: BaseDataConnector,
        folder_rel_path: str,
        *,
        display_path: str,
        stale_record_count: int,
    ) -> None:
        """Schedule a background reconcile once per directory path."""
        key = self._background_task_key(folder, folder_rel_path)
        async with self._background_lock():
            existing = self._background_tasks.get(key)
            if existing is not None and not existing.done():
                logger.debug(
                    "Reconcile background already running for %s/%s",
                    folder.name,
                    display_path,
                )
                return

            logger.info(
                "Reconcile background %s/%s: %d stale entries, returning cached data",
                folder.name,
                display_path,
                stale_record_count,
            )
            task = self._create_background_task(
                self._bg_reconcile(folder, folder_rel_path)
            )
            self._background_tasks[key] = task
            task.add_done_callback(
                lambda done_task: type(self)._release_background_task(key, done_task)
            )

    async def _bg_reconcile(
        self, folder: BaseDataConnector, folder_rel_path: str
    ) -> None:
        """Background reconcile with its own DB session."""
        from database import AsyncSessionLocal
        from rls import internal_context, rls_session

        try:
            async with rls_session(
                AsyncSessionLocal, internal_context("watcher")
            ) as db:
                reconciler = Reconciler(db)
                await reconciler._do_reconcile(folder, folder_rel_path)
        except Exception:
            logger.exception(
                "Background reconcile failed for %s/%s", folder.name, folder_rel_path
            )

    async def _scan_directory(
        self, folder: BaseDataConnector, folder_rel_path: str
    ) -> dict[str, "ContentEntry"]:
        """Scan immediate directory children via the source adapter.

        Returns {relative_path: ContentEntry} for non-hidden entries.
        """
        adapter = folder.get_adapter()
        entries: dict[str, ContentEntry] = {}
        try:
            for entry in await adapter.list_directory(folder_rel_path):
                normalized_path = _normalize_seen_path(entry.relative_path)
                if normalized_path != entry.relative_path:
                    entry = replace(
                        entry,
                        name=normalized_path.rsplit("/", 1)[-1],
                        relative_path=normalized_path,
                    )
                entries[normalized_path] = entry
        except (OSError, PermissionError, FileNotFoundError) as e:
            logger.warning(
                "Reconciliation scan failed for %s/%s: %s",
                folder.name,
                folder_rel_path,
                e,
                exc_info=True,
            )
        return entries

    async def _sync_directory_entry(
        self,
        folder: BaseDataConnector,
        rel_path: str,
        entry: ContentEntry,
        viewers: EffectiveViewers,
    ) -> int:
        await upsert_directory_record(
            self.db,
            folder,
            rel_path,
            entry.is_symlink,
            viewers,
        )
        return 1

    async def _sync_file_entry(
        self,
        folder: BaseDataConnector,
        entry: ContentEntry,
        existing: IndexedContentItem | None,
        task_svc: TaskQueueService,
        viewers: EffectiveViewers,
    ) -> tuple[int, int]:
        result = await sync_observed_file(
            db=self.db,
            task_svc=task_svc,
            folder=folder,
            observed_file=ObservedContentItem.from_entry(folder.uuid, entry),
            record=existing,
            viewers=viewers,
            requeue_if_status_queued=True,
        )
        if result.enqueued:
            return 1, 1
        if result.changed:
            return 1, 0
        return 0, 0

    async def _sync_entry(
        self,
        folder: BaseDataConnector,
        rel_path: str,
        entry: ContentEntry,
        existing: IndexedContentItem | None,
        task_svc: TaskQueueService,
        viewers: EffectiveViewers,
    ) -> tuple[int, int]:
        if entry.is_dir:
            return (
                await self._sync_directory_entry(
                    folder,
                    rel_path,
                    entry,
                    viewers,
                ),
                0,
            )

        if not entry.is_file:
            return 0, 0

        return await self._sync_file_entry(
            folder,
            entry,
            existing,
            task_svc,
            viewers,
        )

    async def _sync_entries(
        self,
        folder: BaseDataConnector,
        entries: dict[str, ContentEntry],
        db_records: dict[str, IndexedContentItem],
        task_svc: TaskQueueService,
        viewers: EffectiveViewers,
    ) -> tuple[int, int]:
        """Upsert scanned entries into the DB and enqueue changed files.

        Returns (upserted_count, enqueued_count).
        """
        upserted = 0
        enqueued = 0

        for rel_path, entry in entries.items():
            existing = db_records.get(rel_path)
            upsert_inc, enqueue_inc = await self._sync_entry(
                folder,
                rel_path,
                entry,
                existing,
                task_svc,
                viewers,
            )
            upserted += upsert_inc
            enqueued += enqueue_inc

        return upserted, enqueued

    async def _remove_stale_records(
        self,
        db_records: dict[str, IndexedContentItem],
        seen_paths: set[str],
        folder: BaseDataConnector,
        display_path: str,
        directory_relative_path: str,
    ) -> int:
        """Delete DB records that no longer exist on disk. Returns count removed."""
        stale_paths = set(db_records.keys()) - seen_paths
        stale_paths.discard(directory_relative_path or "")
        removable_paths: set[str] = set()
        active_paths: set[str] = set()

        for stale_path in stale_paths:
            record = db_records[stale_path]
            if (
                record.processing_status in ACTIVE_PROCESSING_STATUSES
                or await self._has_active_task(record)
            ):
                active_paths.add(stale_path)
                continue
            removable_paths.add(stale_path)
            await ContentDeletionService(self.db).delete_content_path(
                folder_uuid=folder.uuid,
                relative_path=stale_path,
                content_item_id=record.content_item_id,
                source="reconcile",
                metadata={"origin": "reconcile"},
            )

        if removable_paths:
            logger.info(
                "Reconcile %s/%s: removed %d stale entries",
                folder.name,
                display_path,
                len(removable_paths),
            )
        if active_paths:
            logger.info(
                "Reconcile %s/%s: kept %d stale entries with active processing tasks",
                folder.name,
                display_path,
                len(active_paths),
            )
        return len(removable_paths)

    async def _has_active_task(self, record: IndexedContentItem) -> bool:
        """Return True when reconcile must leave this row alone for a worker."""
        stmt = select(TaskQueue.id).where(
            TaskQueue.content_item_id == record.content_item_id,
            TaskQueue.status.in_([TaskStatus.PENDING, TaskStatus.CLAIMED]),
        )
        return (await self.db.execute(stmt)).scalar_one_or_none() is not None

    async def _mark_directory_scanned(
        self,
        folder: BaseDataConnector,
        folder_rel_path: str,
        viewers: EffectiveViewers | None = None,
    ) -> None:
        """Update last_scanned_at on the directory entry."""
        dir_id = compute_content_item_id(folder.uuid, folder_rel_path or "")
        dir_entry = await get_record(self.db, dir_id)
        if dir_entry:
            dir_entry.last_scanned_at = utcnow()
        else:
            if viewers is None:
                viewers = await self._get_effective_viewers(folder.uuid)
            await upsert_directory_entry(
                self.db,
                dir_id,
                folder.uuid,
                folder_rel_path or "",
                allowed_viewers=viewers.allowed_or_none,
                denied_viewers=viewers.denied_or_none,
                auto_commit=False,
            )
            dir_entry = await get_record(self.db, dir_id)
            if dir_entry:
                dir_entry.last_scanned_at = utcnow()

    async def _do_reconcile(
        self, folder: BaseDataConnector, folder_rel_path: str
    ) -> None:
        """Reconcile a single directory (non-recursive) against the storage backend.

        Only scans the immediate children via the adapter — subfolders are
        reconciled lazily when the user browses into them.
        """
        adapter = folder.get_adapter()
        if not await adapter.is_dir(folder_rel_path):
            return

        display_path = folder_rel_path or "(root)"
        logger.info("Reconciling %s/%s (non-recursive)", folder.name, display_path)

        task_svc = TaskQueueService(self.db)
        viewers = await self._get_effective_viewers(folder.uuid)
        db_records = await self._child_db_records(
            folder.uuid,
            folder_rel_path,
        )

        entries = await self._scan_directory(folder, folder_rel_path)
        upserted, enqueued = await self._sync_entries(
            folder, entries, db_records, task_svc, viewers
        )

        removed = await self._remove_stale_records(
            db_records,
            set(entries.keys()),
            folder,
            display_path,
            folder_rel_path,
        )

        await self._mark_directory_scanned(folder, folder_rel_path, viewers=viewers)

        await self.db.commit()
        logger.info(
            "Reconcile %s/%s complete: %d upserted, %d enqueued, %d removed",
            folder.name,
            display_path,
            upserted,
            enqueued,
            removed,
        )
