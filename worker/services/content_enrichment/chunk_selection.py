"""Chunk selection helpers for content enrichment extraction."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

from models import (
    WorkerContentEnrichmentChunkSearchQuery,
    WorkerDocumentExtractionField,
    WorkerDocumentExtractionSchema,
)
from services.backend_client import BackendClient
from services.content_enrichment_utils import (
    MAX_SELECTED_EXTRACTION_CHUNKS,
    _numeric_confidence,
)

logger = logging.getLogger(__name__)
_EXTRACTION_SEARCH_LIMIT_PER_QUERY = 5


def _chunk_index(chunk: Any, fallback: int) -> int:
    value = getattr(chunk, "chunk_index", None)
    return value if isinstance(value, int) else fallback


def _list_attr(chunk: Any, attr: str) -> list[Any]:
    value = getattr(chunk, attr, None)
    return value if isinstance(value, list) else []


def _selected_chunk(
    chunk: Any,
    *,
    fallback_index: int,
    source: str,
    score: float | None = None,
    matched_queries: list[str] | None = None,
) -> Any:
    """Wrap a source chunk with selection metadata while preserving Docling metadata."""
    return SimpleNamespace(
        text=getattr(chunk, "text", ""),
        meta=getattr(chunk, "meta", None),
        chunk_index=_chunk_index(chunk, fallback_index),
        page_numbers=_list_attr(chunk, "page_numbers"),
        doc_refs=_list_attr(chunk, "doc_refs"),
        images=_list_attr(chunk, "images"),
        headings=_list_attr(chunk, "headings"),
        captions=_list_attr(chunk, "captions"),
        score=score if score is not None else getattr(chunk, "score", None),
        matched_queries=list(
            matched_queries
            if matched_queries is not None
            else _list_attr(chunk, "matched_queries")
        ),
        source=source,
    )


def _non_empty_chunks(chunks: list[Any] | None) -> list[Any]:
    if not chunks:
        return []
    non_empty = []
    for chunk in chunks:
        text = getattr(chunk, "text", None)
        if isinstance(text, str) and text.strip():
            non_empty.append(chunk)
    return non_empty


def _schema_search_queries(
    *,
    schema: WorkerDocumentExtractionSchema,
    document_class: str | None,
) -> list[WorkerContentEnrichmentChunkSearchQuery]:
    def field_summary(field: WorkerDocumentExtractionField) -> str:
        child_summary = "; ".join(
            " ".join(
                part
                for part in (child.name, child.description, f"type: {child.dtype}")
                if isinstance(part, str) and part.strip()
            )
            for child in field.fields
        )
        return " ".join(
            part
            for part in (
                field.name,
                field.description,
                f"required: {field.required}",
                f"type: {field.dtype}",
                f"object fields: {child_summary}" if child_summary else "",
            )
            if isinstance(part, str) and part.strip()
        )

    field_summaries = [field_summary(field) for field in schema.fields]
    class_label = document_class or schema.document_class
    queries = [
        WorkerContentEnrichmentChunkSearchQuery(
            key="schema",
            text=" ".join(
                part
                for part in (
                    f"Document class: {class_label}",
                    f"Extraction schema: {schema.name}",
                    schema.description,
                    "Fields:",
                    "; ".join(field_summaries),
                )
                if isinstance(part, str) and part.strip()
            ),
        )
    ]
    for field in schema.fields:
        queries.append(
            WorkerContentEnrichmentChunkSearchQuery(
                key=f"field:{field.name}",
                text=" ".join(
                    part
                    for part in (
                        f"Document class: {class_label}",
                        f"Find field: {field.name}",
                        field.description,
                        f"Expected type: {field.dtype}",
                    )
                    if isinstance(part, str) and part.strip()
                ),
            )
        )
    return queries


def _lexical_field_terms(field: WorkerDocumentExtractionField) -> list[str]:
    terms: list[str] = []
    for raw in (field.name, field.name.replace("_", " "), field.description):
        normalized = " ".join(raw.strip().casefold().split())
        if normalized and normalized not in terms:
            terms.append(normalized)
    return terms


def _lexical_schema_terms(
    schema: WorkerDocumentExtractionSchema,
) -> list[tuple[str, str]]:
    terms: list[tuple[str, str]] = []
    for field in schema.fields:
        for term in _lexical_field_terms(field):
            terms.append((f"field:{field.name}", term))
    for raw in (schema.name, schema.description, schema.document_class):
        normalized = " ".join(raw.strip().casefold().split())
        if normalized:
            terms.append(("schema", normalized))
    return terms


def _lexical_chunk_matches(
    chunks: list[Any],
    *,
    schema: WorkerDocumentExtractionSchema,
) -> list[Any]:
    terms = _lexical_schema_terms(schema)
    scored_chunks: list[tuple[int, int, list[str], Any]] = []
    for fallback_index, chunk in enumerate(chunks):
        text = getattr(chunk, "text", "")
        if not isinstance(text, str) or not text.strip():
            continue
        normalized_text = " ".join(text.casefold().split())
        matched_queries: list[str] = []
        score = 0
        for key, term in terms:
            if term and term in normalized_text:
                score += 1
                if key not in matched_queries:
                    matched_queries.append(key)
        if score <= 0:
            continue
        scored_chunks.append((score, fallback_index, matched_queries, chunk))
    scored_chunks.sort(key=lambda item: (-item[0], item[1]))
    return [
        _selected_chunk(
            chunk,
            fallback_index=fallback_index,
            source="lexical",
            score=float(score),
            matched_queries=matched_queries,
        )
        for score, fallback_index, matched_queries, chunk in scored_chunks
    ]


def _dedupe_selected_chunks(chunks: list[Any]) -> list[Any]:
    selected: dict[int, Any] = {}
    for fallback_index, chunk in enumerate(chunks):
        chunk_index = _chunk_index(chunk, fallback_index)
        existing = selected.get(chunk_index)
        if existing is None:
            selected[chunk_index] = chunk
            continue
        existing_queries = _list_attr(existing, "matched_queries")
        for query in _list_attr(chunk, "matched_queries"):
            if query not in existing_queries:
                existing_queries.append(query)
        existing_score = _numeric_confidence(getattr(existing, "score", None))
        chunk_score = _numeric_confidence(getattr(chunk, "score", None))
        if chunk_score is not None and (
            existing_score is None or chunk_score > existing_score
        ):
            existing.score = chunk_score
    return list(selected.values())


def _select_extraction_chunks(
    chunks: list[Any] | None,
    *,
    schema: WorkerDocumentExtractionSchema,
    document_class: str | None,
    task_id: str | None,
    task_secret: str | None,
) -> tuple[list[Any] | None, int, str | None]:
    """Select extraction chunks by relevance, falling back to local lexical choices."""
    available_chunks = _non_empty_chunks(chunks)
    if not available_chunks:
        return None, 0, "no_chunks"

    # Without task context the semantic search isn't reachable; lexical alone
    # may miss whole sections, so fall back to all chunks when they fit the
    # selector budget. With task context we always run the full selector.
    if (not task_id or not task_secret) and len(
        available_chunks
    ) <= MAX_SELECTED_EXTRACTION_CHUNKS:
        return (
            [
                _selected_chunk(
                    chunk,
                    fallback_index=index,
                    source="all_chunks",
                    matched_queries=["all_chunks"],
                )
                for index, chunk in enumerate(available_chunks)
            ],
            0,
            None,
        )

    queries = _schema_search_queries(schema=schema, document_class=document_class)
    selected: list[Any] = []
    fallback_reason: str | None = None
    if task_id and task_secret:
        try:
            response = BackendClient().search_content_enrichment_chunks(
                task_id,
                task_secret,
                queries=queries,
                limit_per_query=_EXTRACTION_SEARCH_LIMIT_PER_QUERY,
                final_limit=MAX_SELECTED_EXTRACTION_CHUNKS,
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            fallback_reason = f"semantic_search_failed:{type(exc).__name__}"
            logger.warning(
                "Content extraction semantic chunk search failed",
                extra={"error": str(exc), "schema_name": schema.name},
            )
        else:
            selected = [
                _selected_chunk(
                    chunk,
                    fallback_index=index,
                    source="semantic",
                    score=chunk.score,
                    matched_queries=chunk.matched_queries,
                )
                for index, chunk in enumerate(response.chunks)
            ]
            if not selected:
                fallback_reason = "semantic_search_empty"
    else:
        fallback_reason = "missing_task_context"

    lexical_matches = _lexical_chunk_matches(available_chunks, schema=schema)
    if selected:
        selected = _dedupe_selected_chunks([*lexical_matches, *selected])[
            :MAX_SELECTED_EXTRACTION_CHUNKS
        ]
    else:
        selected = lexical_matches[:MAX_SELECTED_EXTRACTION_CHUNKS]
        if selected:
            fallback_reason = fallback_reason or "lexical"

    if not selected:
        fallback_reason = fallback_reason or "first_non_empty_chunks"
        selected = [
            _selected_chunk(
                chunk,
                fallback_index=index,
                source="first_chunks",
                matched_queries=["first_chunks"],
            )
            for index, chunk in enumerate(
                available_chunks[:MAX_SELECTED_EXTRACTION_CHUNKS]
            )
        ]

    return selected, len(queries), fallback_reason
