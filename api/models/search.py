"""Search-related models."""

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field

from models.content.items import ContentItemKind


class SearchRequest(BaseModel):
    """Search request parameters."""

    query: str
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    content_kind: ContentItemKind | None = None
    extension: Optional[str] = None
    path_prefix: Optional[str] = None
    score_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class SearchResult(BaseModel):
    """Single search result."""

    score: float
    file_path: str
    content_item_id: str | None = None
    display_name: str | None = None
    content_kind: ContentItemKind | None = None
    email_from_address: str | None = None
    email_sent_at: datetime | None = None
    parent_display_name: str | None = None
    text: Optional[str] = None
    chunk_index: int = 0
    page_numbers: list[int] = Field(default_factory=list)
    headings: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    doc_refs: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """Search response with results and metadata."""

    query: str
    results: list[SearchResult]
    total: int
    limit: int
    offset: int
    has_more: bool = False
