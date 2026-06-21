"""Evidence anchor normalization and grounding helpers."""

from __future__ import annotations

import re
from typing import Any

from intextum_worker.models import WorkerDocumentEvidence
from intextum_worker.services.content_enrichment_utils import (
    MAX_EVIDENCE_SNIPPET_CHARS,
    _chunk_index_from_chunk,
    _doc_refs_from_chunk,
    _page_numbers_from_chunk,
)

_MAX_EVIDENCE_ANCHOR_WORDS = 10
_WHITESPACE_RE = re.compile(r"\s+")


def _short_anchor(value: str) -> str:
    """Truncate a verbatim source span to at most the first N words."""
    if not value:
        return ""
    words = value.split()
    if len(words) <= _MAX_EVIDENCE_ANCHOR_WORDS:
        return value.strip()
    return " ".join(words[:_MAX_EVIDENCE_ANCHOR_WORDS]).strip()


def _ground_anchor(
    anchor: str | None,
    selected_text: str,
    chunk_offsets: list[tuple[int, int, Any]],
) -> tuple[list[WorkerDocumentEvidence], str | None]:
    """Locate one anchor in the source text and build evidence records."""
    if not anchor or not selected_text:
        return [], None
    cleaned_anchor = anchor.strip()
    if not cleaned_anchor:
        return [], None
    position = selected_text.find(cleaned_anchor)
    if position < 0:
        position = _fuzzy_locate(cleaned_anchor, selected_text)
    if position < 0:
        return [], cleaned_anchor[:MAX_EVIDENCE_SNIPPET_CHARS]
    # Snippet expands past the anchor to give useful context for the UI.
    snippet_end = min(len(selected_text), position + MAX_EVIDENCE_SNIPPET_CHARS)
    snippet = selected_text[position:snippet_end].strip()
    chunk = _chunk_at_offset(position, chunk_offsets)
    if chunk is None:
        return (
            [WorkerDocumentEvidence(snippet=snippet, source="langgraph")],
            snippet,
        )
    fallback_index = next(
        (idx for idx, (_, _, c) in enumerate(chunk_offsets) if c is chunk),
        0,
    )
    return (
        [
            WorkerDocumentEvidence(
                chunk_index=_chunk_index_from_chunk(chunk, fallback_index),
                page_numbers=_page_numbers_from_chunk(chunk),
                doc_refs=_doc_refs_from_chunk(chunk),
                snippet=snippet,
                source="langgraph",
            )
        ],
        snippet,
    )


def _fuzzy_locate(quote: str, selected_text: str) -> int:
    """Locate `quote` in `selected_text` ignoring whitespace differences."""
    normalized_quote = _WHITESPACE_RE.sub(" ", quote).strip()
    if not normalized_quote:
        return -1
    cursor = 0
    text_len = len(selected_text)
    while cursor < text_len:
        first_word = normalized_quote.split(" ", 1)[0]
        candidate = selected_text.find(first_word, cursor)
        if candidate < 0:
            return -1
        window = selected_text[candidate : candidate + len(quote) * 2]
        normalized_window = _WHITESPACE_RE.sub(" ", window).strip()
        if normalized_window.startswith(normalized_quote):
            return candidate
        cursor = candidate + 1
    return -1


def _chunk_at_offset(
    offset: int,
    chunk_offsets: list[tuple[int, int, Any]],
) -> Any | None:
    for start, end, chunk in chunk_offsets:
        if start <= offset < end:
            return chunk
    return None
