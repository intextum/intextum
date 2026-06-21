"""Mutable request-scoped source collection for one chat generation."""

from dataclasses import dataclass, field, replace
from datetime import datetime

from chat.sources import CollectedSource, build_source_payloads
from models.content.items import ContentItemKind


@dataclass
class ChatSourceCollector:
    """Owns collected citations and numbering for one assistant turn."""

    sources: list[CollectedSource] = field(default_factory=list)
    next_citation_index: int = 1
    _context_sources: dict[str, list[CollectedSource]] = field(default_factory=dict)

    def add_source(self, source: CollectedSource) -> None:
        """Record one collected source for downstream citation emission."""
        self.sources.append(source)

    def prime_context_sources(
        self,
        *,
        key: str,
        sources: list[CollectedSource],
    ) -> list[CollectedSource]:
        """Preload stable context sources once so follow-up answers can cite them."""
        existing = self._context_sources.get(key)
        if existing is not None:
            return existing

        assigned_sources: list[CollectedSource] = []
        seen_keys = {
            (source.content_item_id or source.file_path, source.citation_index)
            for source in self.sources
            if source.file_path or source.content_item_id
        }

        for source in sources:
            if not source.file_path and not source.content_item_id:
                continue

            citation_index = source.citation_index
            if not isinstance(citation_index, int) or citation_index < 1:
                citation_index = self.next_citation_index
            self.next_citation_index = max(self.next_citation_index, citation_index + 1)

            assigned = replace(source, citation_index=citation_index)
            dedupe_key = (
                assigned.content_item_id or assigned.file_path,
                assigned.citation_index,
            )
            if dedupe_key in seen_keys:
                continue

            seen_keys.add(dedupe_key)
            self.sources.append(assigned)
            assigned_sources.append(assigned)

        self._context_sources[key] = assigned_sources
        return assigned_sources

    def add_search_source(
        self,
        *,
        file_path: str,
        content_item_id: str | None,
        display_name: str | None,
        content_kind: ContentItemKind | None,
        email_from_address: str | None,
        email_sent_at: datetime | None,
        parent_display_name: str | None,
        page_numbers: list[int],
        doc_refs: list[str],
        text: str,
        image_urls: list[str],
    ) -> int:
        """Record a search citation and return the index shown to the model."""
        citation_index = self.next_citation_index
        self.next_citation_index += 1
        self.sources.append(
            CollectedSource(
                file_path=file_path,
                content_item_id=content_item_id,
                display_name=display_name,
                content_kind=content_kind,
                email_from_address=email_from_address,
                email_sent_at=email_sent_at,
                parent_display_name=parent_display_name,
                page_numbers=page_numbers,
                doc_refs=doc_refs,
                quote=text[:200],
                citation_index=citation_index,
                image_urls=image_urls,
            )
        )
        return citation_index

    def source_paths(self) -> list[str]:
        """Return all collected source file paths for path disambiguation."""
        return [source.file_path for source in self.sources if source.file_path]

    def has_sources(self) -> bool:
        """Return whether any sources were collected during the run."""
        return bool(self.sources)

    def persisted_payloads(self) -> list[dict[str, object]]:
        """Build the stored assistant-message citation payloads."""
        return build_source_payloads(self.sources)
