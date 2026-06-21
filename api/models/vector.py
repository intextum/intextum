"""Typed vector payloads shared across worker, search, and file APIs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class VectorChunkUpsert(BaseModel):
    """Normalized chunk payload written into the vector store."""

    model_config = ConfigDict(extra="ignore")

    id: str
    text: str
    embedding: list[float]
    chunk_index: int = 0
    page_numbers: list[int] | None = None
    headings: list[str] | None = None
    images: list[str] | None = None
    doc_refs: list[str] | None = None
    index_version: str


class VectorSearchHit(BaseModel):
    """Typed semantic-search result returned from the vector store."""

    score: float
    file_path: str
    folder_uuid: str
    content_item_id: str
    display_name: str | None = None
    content_kind: str | None = None
    email_from_address: str | None = None
    email_sent_at: datetime | None = None
    parent_display_name: str | None = None
    text: str = ""
    chunk_index: int = 0
    page_numbers: list[int] = Field(default_factory=list)
    headings: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    doc_refs: list[str] = Field(default_factory=list)


class VectorDocumentChunk(BaseModel):
    """Typed document chunk returned for per-file chunk reads."""

    file_path: str
    content_item_id: str
    display_name: str | None = None
    content_kind: str | None = None
    email_from_address: str | None = None
    email_sent_at: datetime | None = None
    parent_display_name: str | None = None
    text: str = ""
    chunk_index: int = 0
    page_numbers: list[int] = Field(default_factory=list)
    headings: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    doc_refs: list[str] = Field(default_factory=list)
