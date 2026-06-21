"""Centralized content deletion helpers for indexed rows and derived artifacts."""

from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import delete as sql_delete, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.sqlalchemy_models import IndexedContentItem, TaskQueue
from models.user import User
from services.content.audit import ContentAuditService
from services.utils import compute_content_item_id
from services.vector import VectorService

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ContentDeletionResult:
    """Summary of one backend deletion pass."""

    deleted_record_count: int
    deleted_task_count: int
    cleaned_content_item_ids: tuple[str, ...]


def _cleanup_extracted_data(content_item_id: str) -> None:
    settings = get_settings()
    extracted_dir = Path(settings.EXTRACTED_DATA_DIR) / content_item_id
    if extracted_dir.exists():
        shutil.rmtree(extracted_dir, ignore_errors=True)


def _content_scope(relative_path: str):
    if not relative_path:
        return true()
    return or_(
        IndexedContentItem.relative_path == relative_path,
        IndexedContentItem.relative_path.like(f"{relative_path}/%"),
    )


def _task_scope(relative_path: str):
    if not relative_path:
        return true()
    return or_(
        TaskQueue.relative_path == relative_path,
        TaskQueue.relative_path.like(f"{relative_path}/%"),
    )


def _cleanup_content_item_ids(
    records: list[IndexedContentItem],
    fallback_content_item_id: str | None,
) -> tuple[str, ...]:
    ids: list[str] = []
    seen: set[str] = set()
    for record in records:
        if record.is_dir or record.content_item_id in seen:
            continue
        seen.add(record.content_item_id)
        ids.append(record.content_item_id)
    if ids or not fallback_content_item_id:
        return tuple(ids)
    return (fallback_content_item_id,)


class ContentDeletionService:
    """Delete indexed content rows and their derived backend state consistently."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = ContentAuditService(db)

    async def _matching_records(
        self,
        *,
        folder_uuid: str,
        relative_path: str,
    ) -> list[IndexedContentItem]:
        stmt = (
            select(IndexedContentItem)
            .where(
                IndexedContentItem.folder_uuid == folder_uuid,
                _content_scope(relative_path),
            )
            .order_by(func.length(IndexedContentItem.relative_path).desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    @staticmethod
    def _record_summary(record: IndexedContentItem) -> str:
        display_name = record.display_name or record.name or record.relative_path
        return f"Deleted {display_name}"

    async def _append_audit_events(
        self,
        records: list[IndexedContentItem],
        *,
        root_relative_path: str,
        user: User | None,
        actor_sub: str | None,
        actor_name: str | None,
        source: str,
        metadata: dict[str, Any] | None,
    ) -> None:
        for record in records:
            event_metadata = dict(metadata or {})
            if root_relative_path and record.relative_path != root_relative_path:
                event_metadata.setdefault("cascade_root_path", root_relative_path)
            await self.audit.append_event(
                content_item_id=record.content_item_id,
                connector_uuid=record.folder_uuid,
                relative_path=record.relative_path,
                display_name=record.display_name or record.name or record.relative_path,
                event_type="content.deleted",
                event_group="content",
                status="completed",
                summary=self._record_summary(record),
                metadata=event_metadata,
                actor_sub=actor_sub,
                actor_name=actor_name,
                user=user,
                source=source,
                auto_commit=False,
            )

    async def _append_fallback_audit_event(
        self,
        *,
        content_item_id: str,
        folder_uuid: str,
        relative_path: str,
        display_name: str | None,
        user: User | None,
        actor_sub: str | None,
        actor_name: str | None,
        source: str,
        metadata: dict[str, Any] | None,
    ) -> None:
        label = (
            display_name or Path(relative_path).name or relative_path or content_item_id
        )
        await self.audit.append_event(
            content_item_id=content_item_id,
            connector_uuid=folder_uuid,
            relative_path=relative_path,
            display_name=label,
            event_type="content.deleted",
            event_group="content",
            status="completed",
            summary=f"Deleted {label}",
            metadata=metadata,
            actor_sub=actor_sub,
            actor_name=actor_name,
            user=user,
            source=source,
            auto_commit=False,
        )

    async def _delete_task_rows(
        self,
        *,
        folder_uuid: str,
        relative_path: str,
        content_item_ids: set[str],
    ) -> int:
        filters = [TaskQueue.folder_uuid == folder_uuid, _task_scope(relative_path)]
        if content_item_ids:
            filters.append(
                or_(
                    TaskQueue.content_item_id.is_(None),
                    TaskQueue.content_item_id.in_(content_item_ids),
                )
            )
        result = await self.db.execute(sql_delete(TaskQueue).where(*filters))
        return int(result.rowcount or 0)

    async def _cleanup_artifacts_best_effort(
        self,
        *,
        content_item_ids: tuple[str, ...],
        root_relative_path: str,
        folder_uuid: str,
    ) -> None:
        for content_item_id in content_item_ids:
            try:
                await VectorService.delete_chunks(self.db, content_item_id)
            except Exception:
                logger.exception(
                    "Failed to delete vector chunks for %s (%s/%s)",
                    content_item_id,
                    folder_uuid,
                    root_relative_path,
                )
            try:
                await asyncio.to_thread(_cleanup_extracted_data, content_item_id)
            except Exception:
                logger.exception(
                    "Failed to delete extracted artifacts for %s (%s/%s)",
                    content_item_id,
                    folder_uuid,
                    root_relative_path,
                )

    async def delete_content_path(
        self,
        *,
        folder_uuid: str,
        relative_path: str,
        content_item_id: str | None = None,
        display_name: str | None = None,
        user: User | None = None,
        actor_sub: str | None = None,
        actor_name: str | None = None,
        source: str = "backend",
        metadata: dict[str, Any] | None = None,
    ) -> ContentDeletionResult:
        """Delete one file or directory tree from backend-managed state."""
        resolved_content_item_id = content_item_id or compute_content_item_id(
            folder_uuid, relative_path
        )
        records = await self._matching_records(
            folder_uuid=folder_uuid,
            relative_path=relative_path,
        )
        cleanup_ids = _cleanup_content_item_ids(records, resolved_content_item_id)

        deleted_task_count = await self._delete_task_rows(
            folder_uuid=folder_uuid,
            relative_path=relative_path,
            content_item_ids=set(cleanup_ids),
        )

        if records:
            await self._append_audit_events(
                records,
                root_relative_path=relative_path,
                user=user,
                actor_sub=actor_sub,
                actor_name=actor_name,
                source=source,
                metadata=metadata,
            )
            for record in records:
                await self.db.delete(record)
        elif resolved_content_item_id:
            await self._append_fallback_audit_event(
                content_item_id=resolved_content_item_id,
                folder_uuid=folder_uuid,
                relative_path=relative_path,
                display_name=display_name,
                user=user,
                actor_sub=actor_sub,
                actor_name=actor_name,
                source=source,
                metadata=metadata,
            )

        await self.db.commit()
        await self._cleanup_artifacts_best_effort(
            content_item_ids=cleanup_ids,
            root_relative_path=relative_path,
            folder_uuid=folder_uuid,
        )
        return ContentDeletionResult(
            deleted_record_count=len(records),
            deleted_task_count=deleted_task_count,
            cleaned_content_item_ids=cleanup_ids,
        )
