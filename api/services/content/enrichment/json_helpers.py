"""Shared helpers for normalized content enrichment state."""

from __future__ import annotations

from typing import Any

from models.sqlalchemy_models import ContentItemEnrichmentState, IndexedContentItem

REVIEW_STATUSES = {"accepted", "corrected", "dismissed"}
MISSING_VALUE_PLACEHOLDERS = {
    "-",
    "--",
    "n/a",
    "na",
    "n.a.",
    "none",
    "null",
    "unknown",
    "not applicable",
    "not available",
    "not provided",
    "not specified",
    "nicht angegeben",
    "keine angabe",
    "k. a.",
    "k.a.",
}


def json_object(value: Any) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, dict) else None


def json_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def json_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def normalized_lookup(value: str | None) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def classification_label(payload: dict[str, Any] | None) -> str | None:
    return string(payload.get("label")) if payload is not None else None


def payload_document_class(payload: dict[str, Any] | None) -> str | None:
    return string(payload.get("document_class")) if payload is not None else None


def value_is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        normalized = " ".join(value.split()).casefold()
        return not normalized or normalized in MISSING_VALUE_PLACEHOLDERS
    if isinstance(value, list):
        return len(value) == 0
    return False


def infer_dtype(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, list):
        return "list"
    return "str"


def review_reason(code: str, *, fields: list[str] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code}
    if fields:
        payload["fields"] = fields
    return payload


def ensure_state(record: IndexedContentItem) -> ContentItemEnrichmentState:
    state = record.enrichment_state
    if state is None:
        state = ContentItemEnrichmentState(content_item_id=record.content_item_id)
        record.enrichment_state = state
    return state


def sorted_field_names(data: dict[str, Any] | None) -> list[str] | None:
    if not isinstance(data, dict):
        return None
    return sorted(field_name for field_name in data if isinstance(field_name, str))
