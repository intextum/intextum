"""Typed adapters for vector-search chunk payloads used by chat tools."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

from chat.payloads import datetime_or_none, int_list, string_list
from models.content.items import ContentItemKind
from models.vector import VectorDocumentChunk, VectorSearchHit
from services.content.invariants import safe_content_item_kind


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


@dataclass(frozen=True)
class RetrievedChunk:
    """Normalized vector-search result used inside the chat tool layer."""

    text: str = ""
    score: float | None = None
    file_path: str = "unknown"
    folder_uuid: str = ""
    content_item_id: str = ""
    display_name: str = "unknown"
    content_kind: ContentItemKind = ContentItemKind.FILE
    email_from_address: str | None = None
    email_sent_at: datetime | None = None
    parent_display_name: str | None = None
    page_numbers: list[int] = field(default_factory=list)
    doc_refs: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)

    @classmethod
    def from_raw(cls, raw_chunk: Any) -> "RetrievedChunk | None":
        """Parse one vector-search payload into a typed chat chunk."""
        if isinstance(raw_chunk, (VectorSearchHit, VectorDocumentChunk)):
            return cls(
                text=raw_chunk.text,
                score=raw_chunk.score
                if isinstance(raw_chunk, VectorSearchHit)
                else None,
                file_path=raw_chunk.file_path or "unknown",
                folder_uuid=(
                    raw_chunk.folder_uuid
                    if isinstance(raw_chunk, VectorSearchHit)
                    else ""
                ),
                content_item_id=raw_chunk.content_item_id,
                display_name=raw_chunk.display_name
                or PurePosixPath(raw_chunk.file_path or "unknown").name
                or (raw_chunk.file_path or "unknown"),
                content_kind=safe_content_item_kind(raw_chunk.content_kind),
                email_from_address=raw_chunk.email_from_address,
                email_sent_at=raw_chunk.email_sent_at,
                parent_display_name=raw_chunk.parent_display_name,
                page_numbers=list(raw_chunk.page_numbers),
                doc_refs=list(raw_chunk.doc_refs),
                images=list(raw_chunk.images),
            )

        if not isinstance(raw_chunk, dict):
            return None

        file_path = raw_chunk.get("file_path")
        raw_content_kind = raw_chunk.get("content_kind")
        return cls(
            text=raw_chunk.get("text")
            if isinstance(raw_chunk.get("text"), str)
            else "",
            score=_float_or_none(raw_chunk.get("score")),
            file_path=file_path
            if isinstance(file_path, str) and file_path
            else "unknown",
            folder_uuid=(
                raw_chunk.get("folder_uuid")
                if isinstance(raw_chunk.get("folder_uuid"), str)
                else ""
            ),
            content_item_id=raw_chunk.get("content_item_id")
            if isinstance(raw_chunk.get("content_item_id"), str)
            else "",
            display_name=raw_chunk.get("display_name")
            if isinstance(raw_chunk.get("display_name"), str)
            else (
                PurePosixPath(file_path).name
                if isinstance(file_path, str) and file_path
                else "unknown"
            ),
            content_kind=safe_content_item_kind(raw_content_kind),
            email_from_address=raw_chunk.get("email_from_address")
            if isinstance(raw_chunk.get("email_from_address"), str)
            else None,
            email_sent_at=(datetime_or_none(raw_chunk.get("email_sent_at"))),
            parent_display_name=raw_chunk.get("parent_display_name")
            if isinstance(raw_chunk.get("parent_display_name"), str)
            else None,
            page_numbers=int_list(raw_chunk.get("page_numbers")),
            doc_refs=string_list(raw_chunk.get("doc_refs")),
            images=string_list(raw_chunk.get("images")),
        )

    def resolved_file_path(self, folder_uuid_to_name: dict[str, str]) -> str:
        """Return the folder-name-prefixed path shown to the model and UI."""
        folder_name = folder_uuid_to_name.get(self.folder_uuid)
        if folder_name and self.file_path != "unknown":
            return f"{folder_name}/{self.file_path}"
        return self.file_path

    def image_urls(self) -> list[str]:
        """Return extracted-asset URLs for any chunk images."""
        if not self.content_item_id:
            return []

        urls: list[str] = []
        seen_urls: set[str] = set()
        for image in self.images:
            image_filename = image.split("/")[-1] if "/" in image else image
            url = (
                f"/api/content/extracted-asset/{self.content_item_id}/{image_filename}"
            )
            if url not in seen_urls:
                urls.append(url)
                seen_urls.add(url)
        return urls


def parse_retrieved_chunks(raw_chunks: Any) -> list[RetrievedChunk]:
    """Parse a vector-search result list into typed chat chunks."""
    if not isinstance(raw_chunks, list):
        return []

    chunks: list[RetrievedChunk] = []
    for raw_chunk in raw_chunks:
        chunk = RetrievedChunk.from_raw(raw_chunk)
        if chunk is not None:
            chunks.append(chunk)
    return chunks
