"""Typed export payloads for assistant-response downloads."""

from pydantic import BaseModel, Field


class EmbeddedExportImage(BaseModel):
    """One markdown-embedded image asset prepared by the browser for DOCX export."""

    url: str = Field(min_length=1)
    filename: str = Field(min_length=1, max_length=240)
    media_type: str = Field(min_length=1, max_length=120)
    data_base64: str = Field(min_length=1)
    width_px: int = Field(ge=1, le=20000)
    height_px: int = Field(ge=1, le=20000)
    alt_text: str | None = Field(default=None, max_length=240)


class AssistantResponseExportRequest(BaseModel):
    """Normalized export payload shared by Markdown and DOCX generation."""

    title: str = Field(min_length=1, max_length=240)
    filename_base: str = Field(min_length=1, max_length=240)
    markdown: str = Field(min_length=1)
    embedded_images: list[EmbeddedExportImage] = Field(default_factory=list)
