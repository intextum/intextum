"""Source metadata helpers for streamed and persisted chat output."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

from models.conversation import ConversationSource, SourceKind
from models.content.items import ContentItemKind
from chat.payloads import datetime_or_none, int_list, string_list
from services.content.invariants import safe_content_item_kind


@dataclass(frozen=True)
class CollectedSource:
    """Internal request-scoped source record collected during one chat run."""

    file_path: str
    content_item_id: str | None = None
    display_name: str | None = None
    content_kind: ContentItemKind | None = None
    email_from_address: str | None = None
    email_sent_at: datetime | None = None
    parent_display_name: str | None = None
    source_kind: SourceKind | None = None
    page_numbers: list[int] = field(default_factory=list)
    doc_refs: list[str] = field(default_factory=list)
    quote: str = ""
    citation_index: int | str | None = None
    image_urls: list[str] = field(default_factory=list)
    title: str | None = None


@dataclass(frozen=True)
class StoredSourcePayload:
    """Typed citation payload persisted on assistant messages."""

    file_path: str
    content_item_id: str | None = None
    display_name: str | None = None
    content_kind: ContentItemKind | None = None
    email_from_address: str | None = None
    email_sent_at: datetime | None = None
    parent_display_name: str | None = None
    title: str | None = None
    source_kind: SourceKind | None = None
    page_numbers: list[int] = field(default_factory=list)
    doc_refs: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    citation_index: int | str | None = None
    quote: str | None = None

    @classmethod
    def from_collected_source(cls, source: CollectedSource) -> "StoredSourcePayload":
        """Build a persisted payload from one collected runtime source."""
        file_path = source.file_path or "unknown"
        filename = PurePosixPath(file_path).name if file_path else "unknown"
        display_name = (
            source.display_name
            if isinstance(source.display_name, str)
            and source.display_name.strip()
            and source.display_name != "unknown"
            else filename
        )
        return cls(
            file_path=file_path,
            content_item_id=source.content_item_id,
            display_name=display_name,
            content_kind=source.content_kind,
            email_from_address=source.email_from_address,
            email_sent_at=source.email_sent_at,
            parent_display_name=source.parent_display_name,
            title=source.title or display_name or filename,
            source_kind=source.source_kind,
            page_numbers=list(source.page_numbers),
            doc_refs=list(source.doc_refs),
            images=list(source.image_urls),
            citation_index=source.citation_index,
            quote=source.quote,
        )

    @classmethod
    def from_raw(cls, raw_source: Any) -> "StoredSourcePayload | None":
        """Parse one persisted payload from message additional kwargs."""
        if not isinstance(raw_source, dict):
            return None

        file_path = raw_source.get("file_path")
        if not isinstance(file_path, str) or not file_path:
            return None

        raw_citation_index = raw_source.get("citation_index")
        citation_index = (
            raw_citation_index if isinstance(raw_citation_index, (int, str)) else None
        )
        raw_source_kind = raw_source.get("source_kind")
        source_kind = (
            raw_source_kind if raw_source_kind == "reviewed_enrichment" else None
        )
        raw_content_kind = raw_source.get("content_kind")
        content_kind = (
            safe_content_item_kind(raw_content_kind) if raw_content_kind else None
        )

        return cls(
            file_path=file_path,
            content_item_id=raw_source.get("content_item_id")
            if isinstance(raw_source.get("content_item_id"), str)
            else None,
            display_name=raw_source.get("display_name")
            if isinstance(raw_source.get("display_name"), str)
            else None,
            content_kind=content_kind,
            email_from_address=raw_source.get("email_from_address")
            if isinstance(raw_source.get("email_from_address"), str)
            else None,
            email_sent_at=datetime_or_none(raw_source.get("email_sent_at")),
            parent_display_name=raw_source.get("parent_display_name")
            if isinstance(raw_source.get("parent_display_name"), str)
            else None,
            title=raw_source.get("title")
            if isinstance(raw_source.get("title"), str)
            else None,
            source_kind=source_kind,
            page_numbers=int_list(raw_source.get("page_numbers")),
            doc_refs=string_list(raw_source.get("doc_refs")),
            images=string_list(raw_source.get("images")),
            citation_index=citation_index,
            quote=raw_source.get("quote")
            if isinstance(raw_source.get("quote"), str)
            else None,
        )

    def dedupe_key(self) -> tuple[str, int | str | None]:
        """Return the stable key used to collapse duplicate citations."""
        return (self.content_item_id or self.file_path, self.citation_index)

    def to_message_payload(self) -> dict[str, Any]:
        """Serialize this payload into the assistant-message kwargs shape."""
        payload = {
            "file_path": self.file_path,
            "title": self.title,
            "page_numbers": self.page_numbers,
            "doc_refs": self.doc_refs,
            "images": self.images,
            "citation_index": self.citation_index,
            "quote": self.quote,
        }
        if self.content_item_id is not None:
            payload["content_item_id"] = self.content_item_id
        if self.display_name is not None:
            payload["display_name"] = self.display_name
        if self.content_kind is not None:
            payload["content_kind"] = self.content_kind.value
        if self.email_from_address is not None:
            payload["email_from_address"] = self.email_from_address
        if self.email_sent_at is not None:
            payload["email_sent_at"] = self.email_sent_at.isoformat()
        if self.parent_display_name is not None:
            payload["parent_display_name"] = self.parent_display_name
        if self.source_kind is not None:
            payload["source_kind"] = self.source_kind
        return payload

    def to_collected_source(
        self,
        *,
        citation_index: int | str | None = None,
    ) -> CollectedSource:
        """Convert this stored payload back into one request-scoped source record."""
        return CollectedSource(
            file_path=self.file_path,
            content_item_id=self.content_item_id,
            display_name=self.display_name,
            content_kind=self.content_kind,
            email_from_address=self.email_from_address,
            email_sent_at=self.email_sent_at,
            parent_display_name=self.parent_display_name,
            source_kind=self.source_kind,
            page_numbers=list(self.page_numbers),
            doc_refs=list(self.doc_refs),
            quote=self.quote or "",
            citation_index=self.citation_index
            if citation_index is None
            else citation_index,
            image_urls=list(self.images),
            title=self.title,
        )

    def to_conversation_source(self) -> ConversationSource:
        """Convert this stored payload into the frontend API citation model."""
        return ConversationSource(
            file_path=self.file_path,
            content_item_id=self.content_item_id,
            display_name=self.display_name,
            content_kind=self.content_kind,
            email_from_address=self.email_from_address,
            email_sent_at=self.email_sent_at,
            parent_display_name=self.parent_display_name,
            title=self.title,
            source_kind=self.source_kind,
            page_numbers=list(self.page_numbers),
            doc_refs=list(self.doc_refs),
            citation_index=self.citation_index
            if isinstance(self.citation_index, int)
            else None,
            images=list(self.images),
            quote=self.quote,
        )


def build_source_payload(source: CollectedSource) -> dict[str, Any]:
    """Convert a collected source into the frontend citation payload."""
    return StoredSourcePayload.from_collected_source(source).to_message_payload()


def build_source_payloads(sources: list[CollectedSource]) -> list[dict[str, Any]]:
    """Deduplicate collected sources and convert them to chat message payloads."""
    payloads: list[dict[str, Any]] = []
    seen: set[tuple[str, int | str | None]] = set()

    for source in sources:
        if not source.file_path and not source.content_item_id:
            continue

        payload = StoredSourcePayload.from_collected_source(source)
        key = payload.dedupe_key()
        if key in seen:
            continue

        seen.add(key)
        payloads.append(payload.to_message_payload())

    return payloads


def parse_stored_source_payloads(raw_sources: Any) -> list[StoredSourcePayload]:
    """Parse persisted citation payloads from message additional kwargs."""
    if not isinstance(raw_sources, list):
        return []

    payloads: list[StoredSourcePayload] = []
    for raw_source in raw_sources:
        payload = StoredSourcePayload.from_raw(raw_source)
        if payload is not None:
            payloads.append(payload)
    return payloads


def parse_source_payloads(raw_sources: Any) -> list[ConversationSource]:
    """Parse persisted source payloads from message additional kwargs."""
    return [
        payload.to_conversation_source()
        for payload in parse_stored_source_payloads(raw_sources)
    ]
