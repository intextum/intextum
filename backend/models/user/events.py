"""Typed models for generic user-scoped lifecycle events."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UserEventRecord(BaseModel):
    """One lifecycle event delivered to a user event stream."""

    kind: str
    resource_type: str
    resource_id: str
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    event_id: str | None = None

    model_config = ConfigDict(extra="forbid")
