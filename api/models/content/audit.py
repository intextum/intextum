"""Typed API models for content audit events."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ContentAuditEventInfo(BaseModel):
    """One durable content audit event."""

    id: str
    content_item_id: str
    connector_uuid: str | None = None
    relative_path: str | None = None
    display_name: str | None = None
    event_type: str
    event_group: str
    status: str
    summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    actor_sub: str | None = None
    actor_name: str | None = None
    source: str
    created_at: datetime


class ContentAuditEventListResponse(BaseModel):
    """Paginated audit events for one content item."""

    events: list[ContentAuditEventInfo] = Field(default_factory=list)
    total: int = 0
    limit: int
    offset: int
