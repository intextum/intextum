"""Conversation data models."""

from datetime import datetime
from typing import Any, Optional
from typing import Literal

from pydantic import BaseModel, Field

from models.chat import ChatStreamMessage
from models.content.items import ContentItemKind

SourceKind = Literal["reviewed_enrichment"]


class ConversationUpdate(BaseModel):
    """Request model for updating a conversation."""

    title: Optional[str] = None


class ConversationImportRequest(BaseModel):
    """Request model for importing a temporary chat transcript."""

    title: Optional[str] = None
    context_file_paths: list[str] = Field(default_factory=list)
    messages: list[ChatStreamMessage] = Field(default_factory=list)


class ConversationImportResponse(BaseModel):
    """Response model for a newly imported conversation."""

    conversation_id: str


class ConversationSummary(BaseModel):
    """Summary model for sidebar listing."""

    id: str
    title: Optional[str]
    created_at: str
    updated_at: str
    active_run_status: Literal["PENDING", "RUNNING"] | None = None


class ConversationSource(BaseModel):
    """Document citation metadata attached to an assistant message."""

    file_path: str
    content_item_id: str | None = None
    display_name: str | None = None
    content_kind: ContentItemKind | None = None
    email_from_address: str | None = None
    email_sent_at: datetime | None = None
    parent_display_name: str | None = None
    title: str | None = None
    source_kind: SourceKind | None = None
    page_numbers: list[int] = Field(default_factory=list)
    doc_refs: list[str] = Field(default_factory=list)
    citation_index: int | None = None
    images: list[str] = Field(default_factory=list)
    quote: str | None = None


class ConversationMessage(BaseModel):
    """Single chat message used by the frontend conversation view."""

    id: str
    role: str
    content: str
    sources: list[ConversationSource] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None
    created_at: str | None = None
    status: str | None = None


class ConversationDetail(BaseModel):
    """Full conversation with messages."""

    id: str
    title: Optional[str]
    created_at: str
    updated_at: str
    messages: list[ConversationMessage]
    context_file_paths: list[str] = Field(default_factory=list)


class ConversationListResponse(BaseModel):
    """Response model for listing conversations."""

    conversations: list[ConversationSummary]
    total: int


class ConversationBulkDeleteResponse(BaseModel):
    """Response model for deleting all conversations for a user."""

    deleted_count: int
