"""Typed models for resumable conversation run management."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .stream import ChatStreamMessage
from models.enums import ChatRunStatus, ConversationRunMode

ChatRunEventName = Literal[
    "status",
    "messages",
    "values",
    "progress",
    "error",
    "done",
]


class ChatRunRecord(BaseModel):
    """API-safe projection of one persisted chat run."""

    model_config = ConfigDict(use_enum_values=True)

    id: str
    conversation_id: str
    user_sub: str
    mode: ConversationRunMode = ConversationRunMode.CHAT
    research_report_id: str | None = None
    status: ChatRunStatus
    claimed_by: str | None = None
    claimed_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_event_id: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class CreateChatRunResponse(BaseModel):
    """Response returned when a new resumable chat run is created."""

    model_config = ConfigDict(use_enum_values=True)

    run_id: str
    conversation_id: str
    mode: ConversationRunMode = ConversationRunMode.CHAT
    research_report_id: str | None = None
    status: ChatRunStatus


class ChatRunEvent(BaseModel):
    """One logical event persisted for replayable run streaming."""

    event: ChatRunEventName
    payload: Any = None
    run_id: str
    conversation_id: str
    event_id: str | None = None
    created_at: str | None = None


class ChatRunRequestPayload(BaseModel):
    """Serialized normalized chat request stored with a run row."""

    class UserPayload(BaseModel):
        """Minimal authenticated user context needed to rerun a chat request."""

        username: str
        sub: str
        email: str | None = None
        groups: list[str] = Field(default_factory=list)
        is_admin: bool = False
        preferred_username: str | None = None
        uid: int | None = None
        gids: list[int] = Field(default_factory=list)

    conversation_id: str
    mode: ConversationRunMode = ConversationRunMode.CHAT
    research_report_id: str | None = None
    user: UserPayload
    messages: list[ChatStreamMessage] = Field(default_factory=list)
    context_file_paths: list[str] = Field(default_factory=list)
