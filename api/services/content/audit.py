"""Durable content audit trail helpers."""

from __future__ import annotations

import uuid
from inspect import isawaitable
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.content.audit import ContentAuditEventInfo, ContentAuditEventListResponse
from models.sqlalchemy_models import ContentAuditEvent, IndexedContentItem, utc_now
from models.user import User

MAX_SUMMARY_LENGTH = 1_000
MAX_METADATA_STRING_LENGTH = 500
MAX_METADATA_LIST_ITEMS = 20


def _truncate_string(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return f"{value[: max_length - 3]}..."


def _safe_metadata_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _truncate_string(value, MAX_METADATA_STRING_LENGTH)
    if isinstance(value, (list, tuple)):
        return [
            _safe_metadata_value(item) for item in list(value)[:MAX_METADATA_LIST_ITEMS]
        ]
    if isinstance(value, dict):
        return {
            str(key): _safe_metadata_value(item)
            for key, item in list(value.items())[:MAX_METADATA_LIST_ITEMS]
        }
    if isinstance(value, datetime):
        return value.isoformat()
    return _truncate_string(str(value), MAX_METADATA_STRING_LENGTH)


def safe_audit_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Return JSON-safe, summary-sized metadata for audit persistence."""
    if not metadata:
        return {}
    return {
        str(key): _safe_metadata_value(value)
        for key, value in metadata.items()
        if value is not None
    }


def _actor_sub(user: User | None) -> str | None:
    if user is None:
        return None
    return user.normalized_sub or user.sub or user.username


def _audit_event_info(row: ContentAuditEvent) -> ContentAuditEventInfo:
    return ContentAuditEventInfo(
        id=row.id,
        content_item_id=row.content_item_id,
        connector_uuid=row.connector_uuid,
        relative_path=row.relative_path,
        display_name=row.display_name,
        event_type=row.event_type,
        event_group=row.event_group,
        status=row.status,
        summary=row.summary,
        metadata=row.metadata_json or {},
        actor_sub=row.actor_sub,
        actor_name=row.actor_name,
        source=row.source,
        created_at=row.created_at,
    )


class ContentAuditService:
    """Append and read durable content audit events."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def append_event(
        self,
        *,
        content_item_id: str,
        event_type: str,
        event_group: str,
        status: str,
        summary: str,
        connector_uuid: str | None = None,
        relative_path: str | None = None,
        display_name: str | None = None,
        metadata: dict[str, Any] | None = None,
        actor_sub: str | None = None,
        actor_name: str | None = None,
        user: User | None = None,
        source: str = "backend",
        created_at: datetime | None = None,
        auto_commit: bool = False,
    ) -> ContentAuditEventInfo:
        """Append one audit event. Caller owns the surrounding transaction by default."""
        row = ContentAuditEvent(
            id=uuid.uuid4().hex,
            content_item_id=content_item_id,
            connector_uuid=connector_uuid,
            relative_path=relative_path,
            display_name=display_name,
            event_type=event_type,
            event_group=event_group,
            status=status,
            summary=_truncate_string(summary.strip() or event_type, MAX_SUMMARY_LENGTH),
            metadata_json=safe_audit_metadata(metadata),
            actor_sub=actor_sub or _actor_sub(user),
            actor_name=actor_name or (user.display_name if user is not None else None),
            source=source,
            created_at=created_at or utc_now(),
        )
        add_result = self.db.add(row)
        if isawaitable(add_result):
            await add_result
        if auto_commit:
            await self.db.commit()
        return _audit_event_info(row)

    async def append_for_record(
        self,
        record: IndexedContentItem,
        *,
        event_type: str,
        event_group: str,
        status: str,
        summary: str,
        metadata: dict[str, Any] | None = None,
        user: User | None = None,
        actor_sub: str | None = None,
        actor_name: str | None = None,
        source: str = "backend",
        auto_commit: bool = False,
    ) -> ContentAuditEventInfo:
        """Append an event using stable identity fields from an indexed content row."""
        return await self.append_event(
            content_item_id=record.content_item_id,
            connector_uuid=record.folder_uuid,
            relative_path=record.relative_path,
            display_name=record.display_name or record.name or record.relative_path,
            event_type=event_type,
            event_group=event_group,
            status=status,
            summary=summary,
            metadata=metadata,
            user=user,
            actor_sub=actor_sub,
            actor_name=actor_name,
            source=source,
            auto_commit=auto_commit,
        )

    async def list_for_content_item(
        self,
        content_item_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> ContentAuditEventListResponse:
        """Return audit events for one content item, newest first."""
        count_stmt = select(func.count(ContentAuditEvent.id)).where(
            ContentAuditEvent.content_item_id == content_item_id
        )
        total = int((await self.db.execute(count_stmt)).scalar() or 0)
        stmt = (
            select(ContentAuditEvent)
            .where(ContentAuditEvent.content_item_id == content_item_id)
            .order_by(ContentAuditEvent.created_at.desc(), ContentAuditEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return ContentAuditEventListResponse(
            events=[_audit_event_info(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )
