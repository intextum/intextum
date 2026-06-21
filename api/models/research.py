"""Typed models for deep research reports."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from models.content.items import ContentItemKind
from models.conversation import SourceKind
from models.enums import ResearchRunStatus


class ResearchReportSource(BaseModel):
    """Document citation metadata attached to one research report."""

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


class ResearchReportImage(BaseModel):
    """Image selected for inclusion in one research report."""

    url: str
    title: str | None = None
    citation_index: int | None = None


class ResearchReportSection(BaseModel):
    """One section of the final research report."""

    heading: str
    body: str


class ResearchVerification(BaseModel):
    """Validation notes gathered during report assembly."""

    issues: list[str] = Field(default_factory=list)


class ResearchReportSummary(BaseModel):
    """List item returned for one owned research report."""

    id: str
    title: str | None
    prompt: str
    status: ResearchRunStatus
    created_at: str
    updated_at: str
    finished_at: str | None = None


class ResearchReportDetail(BaseModel):
    """Detailed research report payload returned to the frontend."""

    model_config = ConfigDict(use_enum_values=True)

    id: str
    title: str | None
    prompt: str
    status: ResearchRunStatus
    context_file_paths: list[str] = Field(default_factory=list)
    outline: list[str] = Field(default_factory=list)
    sections: list[ResearchReportSection] = Field(default_factory=list)
    sources: list[ResearchReportSource] = Field(default_factory=list)
    images: list[ResearchReportImage] = Field(default_factory=list)
    verification: ResearchVerification = Field(default_factory=ResearchVerification)
    content_markdown: str | None = None
    error_message: str | None = None
    run_id: str | None = None
    created_at: str
    updated_at: str
    finished_at: str | None = None


class ResearchReportListResponse(BaseModel):
    """Response payload for listing owned research reports."""

    reports: list[ResearchReportSummary]
    total: int
