"""Shared helpers for loading effective enrichment on selected context files."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chat.context import ChatContextScope
from models.sqlalchemy_models import IndexedContentItem
from models.user import User
from services.content.enrichment import build_content_enrichment_api_views


def _classification_label(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    label = payload.get("label")
    if isinstance(label, str) and label.strip():
        return label.strip()
    return None


def _source_label(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("source") == "user_override":
        return "user_override"
    return "document_processing"


def _review_status(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    status = payload.get("review_status")
    if status in {"accepted", "corrected", "dismissed"}:
        return str(status)
    return None


def _normalized_page_numbers(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    return [page for page in value if isinstance(page, int)]


def _normalized_doc_refs(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [ref for ref in value if isinstance(ref, str) and ref]


def _normalized_reviewed_evidence_entry(
    raw_evidence: Any,
    *,
    label: str,
) -> dict[str, Any] | None:
    if not isinstance(raw_evidence, dict):
        return None
    snippet = raw_evidence.get("snippet")
    if not isinstance(snippet, str) or not snippet.strip():
        return None
    return {
        "label": label,
        "snippet": snippet.strip(),
        "page_numbers": _normalized_page_numbers(raw_evidence.get("page_numbers")),
        "doc_refs": _normalized_doc_refs(raw_evidence.get("doc_refs")),
    }


def _collect_reviewed_evidence(
    *,
    classification_effective: dict[str, Any] | None,
    extraction_effective: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    reviewed: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    if _review_status(classification_effective) is not None and isinstance(
        classification_effective, dict
    ):
        label = _classification_label(classification_effective)
        evidence_items = classification_effective.get("evidence")
        if isinstance(label, str) and isinstance(evidence_items, list):
            for raw_evidence in evidence_items:
                entry = _normalized_reviewed_evidence_entry(
                    raw_evidence,
                    label=f"Document class: {label}",
                )
                if entry is None:
                    continue
                dedupe_key = (entry["label"], entry["snippet"])
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                reviewed.append(entry)

    if _review_status(extraction_effective) is not None and isinstance(
        extraction_effective, dict
    ):
        fields = extraction_effective.get("fields")
        if isinstance(fields, dict):
            for field_name, field_payload in fields.items():
                if not isinstance(field_name, str) or not isinstance(
                    field_payload, dict
                ):
                    continue
                evidence_items = field_payload.get("evidence")
                if not isinstance(evidence_items, list):
                    continue
                for raw_evidence in evidence_items:
                    entry = _normalized_reviewed_evidence_entry(
                        raw_evidence,
                        label=f"Field {field_name}",
                    )
                    if entry is None:
                        continue
                    dedupe_key = (entry["label"], entry["snippet"])
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    reviewed.append(entry)

    return reviewed


async def load_effective_context_file_enrichment(
    *,
    db: AsyncSession,
    user: User,
    context_scope: ChatContextScope,
) -> list[dict[str, Any]]:
    """Load effective class/extraction data for selected accessible context files."""
    if not context_scope.has_constraints or not context_scope.file_ids:
        return []

    stmt = select(IndexedContentItem).where(
        IndexedContentItem.content_item_id.in_(context_scope.file_ids)
    )
    result = await db.execute(stmt)
    records = {record.content_item_id: record for record in result.scalars().all()}

    items: list[dict[str, Any]] = []
    for (api_path, _, _), content_item_id in zip(
        context_scope.constraints, context_scope.file_ids
    ):
        record = records.get(content_item_id)
        if record is None:
            continue

        classification_effective, extraction_effective, _enrichment = (
            build_content_enrichment_api_views(record)
        )
        classification_payload = (
            classification_effective.model_dump() if classification_effective else None
        )
        extraction_payload = (
            extraction_effective.model_dump() if extraction_effective else None
        )
        classification_label = _classification_label(classification_payload)
        extraction_data = (
            extraction_payload.get("data")
            if isinstance(extraction_payload, dict)
            else None
        )
        if classification_label is None and not (
            isinstance(extraction_data, dict) and extraction_data
        ):
            continue

        items.append(
            {
                "content_item_id": content_item_id,
                "api_path": api_path,
                "document_class": classification_label,
                "document_class_source": _source_label(classification_payload),
                "document_class_review_status": _review_status(classification_payload),
                "extraction_data": extraction_data
                if isinstance(extraction_data, dict)
                else {},
                "extraction_source": _source_label(extraction_payload),
                "extraction_review_status": _review_status(extraction_payload),
                "reviewed_evidence": _collect_reviewed_evidence(
                    classification_effective=classification_payload,
                    extraction_effective=extraction_payload,
                ),
            }
        )

    return items
