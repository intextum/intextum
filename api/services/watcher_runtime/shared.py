"""Shared watcher runtime helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from config import BaseDataConnector, LocalFsDataConnector
from models.sqlalchemy_models import IndexedContentItem
from services.adapters.base import ContentEntry
from services.content.sync import (
    EffectiveViewers,
    build_effective_viewers,
    upsert_directory_record,
)
from services.permission import PermissionService
from services.task_queue import TaskQueueService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceSyncContext:
    db: AsyncSession
    task_svc: TaskQueueService
    folder: BaseDataConnector
    viewers: EffectiveViewers


@dataclass(frozen=True)
class LocalEventContext:
    db: AsyncSession
    task_svc: TaskQueueService
    folder: LocalFsDataConnector
    content_item_id: str
    relative_path: str


async def _get_indexed_content_item(
    db: AsyncSession, content_item_id: str
) -> IndexedContentItem | None:
    stmt = select(IndexedContentItem).where(
        IndexedContentItem.content_item_id == content_item_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _safe_relative_path(path_obj: Path, folder: LocalFsDataConnector) -> str | None:
    """Return folder-relative path only when path is contained by folder root."""
    try:
        return str(path_obj.resolve().relative_to(Path(folder.path).resolve()))
    except ValueError:
        logger.warning(
            "Skipping out-of-root watcher path: %s (folder=%s)", path_obj, folder.path
        )
        return None


async def _get_effective_viewers(
    db: AsyncSession,
    folder_uuid: str,
) -> EffectiveViewers:
    perm_svc = PermissionService(db)
    allowed_viewers, denied_viewers = await perm_svc.compute_effective_viewers(
        folder_uuid
    )
    return build_effective_viewers(allowed_viewers, denied_viewers)


def _visible_entries_by_path(entries: list[ContentEntry]) -> dict[str, ContentEntry]:
    return {
        entry.relative_path: entry
        for entry in entries
        if not entry.name.startswith(".")
    }


async def _load_folder_records(
    db: AsyncSession, folder_uuid: str
) -> dict[str, IndexedContentItem]:
    stmt = select(IndexedContentItem).where(
        IndexedContentItem.folder_uuid == folder_uuid
    )
    result = await db.execute(stmt)
    return {record.relative_path: record for record in result.scalars().all()}


async def _upsert_directory_from_entry(
    db: AsyncSession,
    folder: BaseDataConnector,
    rel_path: str,
    is_symlink: bool,
    viewers: EffectiveViewers,
) -> None:
    await upsert_directory_record(
        db,
        folder,
        rel_path,
        is_symlink,
        viewers,
    )
