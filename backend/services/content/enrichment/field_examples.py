"""Surface stored extractions as candidate examples when authoring schemas."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.content.enrichment_catalog import (
    ContentEnrichmentFieldExampleCandidate,
    ContentEnrichmentFieldExampleCandidatesResponse,
)
from models.sqlalchemy_models import (
    ContentChunk,
    ContentItemEnrichmentState,
    ExtractionSchemaCatalogEntry,
    IndexedContentItem,
)

_MAX_CANDIDATES = 30
_REVIEWED_STATUSES = ("accepted", "corrected")


class UnknownSchemaError(LookupError):
    """Raised when the requested schema is not present in the catalog."""


class UnknownFieldError(LookupError):
    """Raised when the requested field is not present in the schema."""


def _is_object_list_field(field_payload: dict[str, Any]) -> bool:
    return field_payload.get("dtype") == "object_list"


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _stringify_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return _stable_json(value)


def _value_key(value: Any) -> str:
    """Stable hash-like key used to deduplicate candidates that carry the same value."""
    if isinstance(value, dict):
        return _stable_json(value)
    if isinstance(value, list):
        return _stable_json(value)
    return _stringify_value(value).strip().casefold()


def _find_anchor_in_text(value: Any, text: str) -> str | None:
    """Pick the substring of `text` that grounds `value`, or None when nothing matches."""
    candidates: list[str] = []
    if isinstance(value, str):
        candidates.append(value)
    elif isinstance(value, dict):
        for raw in value.values():
            if isinstance(raw, str) and raw.strip():
                candidates.append(raw)
    elif isinstance(value, (int, float, bool)):
        candidates.append(_stringify_value(value))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                candidates.append(item)
    for candidate in candidates:
        normalized = candidate.strip()
        if normalized and normalized in text:
            return normalized
    return None


def _newest_first_key(state: ContentItemEnrichmentState) -> str:
    """Sort reviewed states with the most recently updated first."""
    updated_at = state.updated_at.isoformat() if state.updated_at else ""
    # Inverting via the str -> "newer first" is awkward; the calling sort uses reverse=True.
    return updated_at


class ContentEnrichmentFieldExampleService:
    """Build candidate field examples from stored extraction records."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def suggest_candidates(
        self,
        *,
        schema_name: str,
        field_name: str,
        content_item_ids: list[str],
    ) -> ContentEnrichmentFieldExampleCandidatesResponse:
        """Return up to MAX_CANDIDATES candidates for one field across the given files."""
        schema_payload = await self._load_schema_payload(schema_name)
        field_payload = self._find_field_payload(schema_payload, field_name)

        if not content_item_ids:
            return ContentEnrichmentFieldExampleCandidatesResponse(candidates=[])

        states = await self._load_states(schema_name, content_item_ids)
        if not states:
            return ContentEnrichmentFieldExampleCandidatesResponse(candidates=[])

        chunks_by_file = await self._chunks_by_file_id(
            [state.content_item_id for state in states]
        )

        seen_values: set[str] = set()
        candidates: list[ContentEnrichmentFieldExampleCandidate] = []
        for state in sorted(states, key=_newest_first_key, reverse=True):
            file_chunks = chunks_by_file.get(state.content_item_id, {})
            if not file_chunks:
                continue
            relative_path = (
                state.content_item.relative_path if state.content_item else ""
            )

            for candidate in self._extract_candidates_from_state(
                state=state,
                field_payload=field_payload,
                file_chunks=file_chunks,
                relative_path=relative_path,
            ):
                key = _value_key(candidate.value)
                if key in seen_values:
                    continue
                seen_values.add(key)
                candidates.append(candidate)
                if len(candidates) >= _MAX_CANDIDATES:
                    return ContentEnrichmentFieldExampleCandidatesResponse(
                        candidates=candidates
                    )

        return ContentEnrichmentFieldExampleCandidatesResponse(candidates=candidates)

    async def _load_schema_payload(self, schema_name: str) -> dict[str, Any]:
        normalized = schema_name.strip()
        if not normalized:
            raise UnknownSchemaError(schema_name)
        result = await self.db.execute(
            select(ExtractionSchemaCatalogEntry).where(
                ExtractionSchemaCatalogEntry.name == normalized
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise UnknownSchemaError(schema_name)
        return {
            "name": row.name,
            "fields": list(row.fields_json or []),
        }

    @staticmethod
    def _find_field_payload(
        schema_payload: dict[str, Any], field_name: str
    ) -> dict[str, Any]:
        for field in schema_payload.get("fields", []):
            if isinstance(field, dict) and field.get("name") == field_name:
                return field
        raise UnknownFieldError(field_name)

    async def _load_states(
        self, schema_name: str, content_item_ids: list[str]
    ) -> list[ContentItemEnrichmentState]:
        result = await self.db.execute(
            select(ContentItemEnrichmentState)
            .options(selectinload(ContentItemEnrichmentState.content_item))
            .join(
                IndexedContentItem,
                ContentItemEnrichmentState.content_item_id
                == IndexedContentItem.content_item_id,
            )
            .where(
                ContentItemEnrichmentState.content_item_id.in_(content_item_ids),
                ContentItemEnrichmentState.extraction_effective_schema_name
                == schema_name,
                ContentItemEnrichmentState.extraction_review_status.in_(
                    _REVIEWED_STATUSES
                ),
            )
        )
        return list(result.scalars().all())

    async def _chunks_by_file_id(
        self, content_item_ids: list[str]
    ) -> dict[str, dict[int, str]]:
        if not content_item_ids:
            return {}
        result = await self.db.execute(
            select(
                ContentChunk.content_item_id,
                ContentChunk.chunk_index,
                ContentChunk.text,
            ).where(ContentChunk.content_item_id.in_(content_item_ids))
        )
        grouped: dict[str, dict[int, str]] = {}
        for content_item_id, chunk_index, text in result.all():
            if not isinstance(content_item_id, str) or not isinstance(text, str):
                continue
            if not isinstance(chunk_index, int):
                continue
            grouped.setdefault(content_item_id, {})[chunk_index] = text
        return grouped

    def _extract_candidates_from_state(
        self,
        *,
        state: ContentItemEnrichmentState,
        field_payload: dict[str, Any],
        file_chunks: dict[int, str],
        relative_path: str,
    ) -> list[ContentEnrichmentFieldExampleCandidate]:
        fields_json = state.extraction_fields_json or {}
        field_name = field_payload["name"]
        field_result = (
            fields_json.get(field_name) if isinstance(fields_json, dict) else None
        )
        if not isinstance(field_result, dict):
            return []

        value = field_result.get("value")
        if value is None or value == "" or value == [] or value == {}:
            return []

        evidence_entries = (
            field_result.get("evidence", [])
            if isinstance(field_result.get("evidence"), list)
            else []
        )

        if _is_object_list_field(field_payload) and isinstance(value, list):
            return self._object_list_candidates(
                state=state,
                rows=value,
                evidence_entries=evidence_entries,
                file_chunks=file_chunks,
                relative_path=relative_path,
            )

        return self._scalar_candidates(
            state=state,
            value=value,
            evidence_entries=evidence_entries,
            file_chunks=file_chunks,
            relative_path=relative_path,
        )

    def _scalar_candidates(
        self,
        *,
        state: ContentItemEnrichmentState,
        value: Any,
        evidence_entries: list[Any],
        file_chunks: dict[int, str],
        relative_path: str,
    ) -> list[ContentEnrichmentFieldExampleCandidate]:
        chunk_text, evidence_meta = self._pick_chunk_for_evidence(
            evidence_entries, file_chunks
        )
        if chunk_text is None:
            return []
        anchor = _find_anchor_in_text(value, chunk_text)
        if anchor is None:
            return []
        return [
            ContentEnrichmentFieldExampleCandidate(
                content_item_id=state.content_item_id,
                relative_path=relative_path,
                review_status=state.extraction_review_status,
                text=chunk_text,
                anchor_text=anchor,
                value=value,
                page_numbers=list(evidence_meta.get("page_numbers", []) or []),
                chunk_index=evidence_meta.get("chunk_index"),
            )
        ]

    def _object_list_candidates(
        self,
        *,
        state: ContentItemEnrichmentState,
        rows: list[Any],
        evidence_entries: list[Any],
        file_chunks: dict[int, str],
        relative_path: str,
    ) -> list[ContentEnrichmentFieldExampleCandidate]:
        results: list[ContentEnrichmentFieldExampleCandidate] = []
        for row_index, row in enumerate(rows):
            if not isinstance(row, dict) or not row:
                continue
            evidence_for_row = (
                evidence_entries[row_index]
                if row_index < len(evidence_entries)
                else None
            )
            if isinstance(evidence_for_row, dict):
                chunk_text, evidence_meta = self._pick_chunk_for_evidence(
                    [evidence_for_row], file_chunks
                )
            else:
                chunk_text, evidence_meta = self._pick_chunk_for_evidence(
                    evidence_entries, file_chunks
                )
            if chunk_text is None:
                continue
            anchor = _find_anchor_in_text(row, chunk_text)
            if anchor is None:
                continue
            results.append(
                ContentEnrichmentFieldExampleCandidate(
                    content_item_id=state.content_item_id,
                    relative_path=relative_path,
                    review_status=state.extraction_review_status,
                    text=chunk_text,
                    anchor_text=anchor,
                    value=row,
                    page_numbers=list(evidence_meta.get("page_numbers", []) or []),
                    chunk_index=evidence_meta.get("chunk_index"),
                )
            )
        return results

    @staticmethod
    def _pick_chunk_for_evidence(
        evidence_entries: list[Any],
        file_chunks: dict[int, str],
    ) -> tuple[str | None, dict[str, Any]]:
        """Return (chunk_text, evidence_dict) for the first evidence entry that resolves."""
        for entry in evidence_entries:
            if not isinstance(entry, dict):
                continue
            chunk_index = entry.get("chunk_index")
            if not isinstance(chunk_index, int):
                continue
            text = file_chunks.get(chunk_index)
            if isinstance(text, str) and text.strip():
                return text, entry
        return None, {}
