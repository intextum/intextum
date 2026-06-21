"""Provider-agnostic validation for worker extraction output."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from models.ai_settings import DocumentExtractionField, DocumentExtractionSchema
from models.ai_settings import EffectiveAiSettings

from .json_helpers import json_dict, string, value_is_empty


@dataclass(frozen=True)
class ValidatedExtractionPayload:
    """Normalized extraction state ready to persist."""

    status: str
    provider: str | None
    model: str | None
    schema_id: str | None
    schema_name: str | None
    schema_version: int | None
    class_id: str | None
    class_label: str | None
    data: dict[str, Any]
    fields: dict[str, dict[str, Any]]
    summary: dict[str, Any]
    raw: dict[str, Any]
    error: str | None
    trusted: bool


@dataclass(frozen=True)
class _ValidatedExtractionField:
    """Normalized extraction state for one schema field."""

    value: Any
    should_store_value: bool
    field_payload: dict[str, Any]
    missing_required_fields: list[str]
    invalid_fields: list[str]
    conflicted: bool
    lacks_evidence: bool


def _normalized(value: str | None) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def _payload_status(payload: dict[str, Any]) -> str:
    status = string(payload.get("status")) or "failed"
    return status if status in {"completed", "skipped", "failed"} else "failed"


def _schema_version(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _schema_for_class(
    settings: EffectiveAiSettings,
    *,
    class_id: str | None,
    class_label: str | None,
) -> DocumentExtractionSchema | None:
    normalized_id = _normalized(class_id)
    normalized_label = _normalized(class_label)
    for schema in settings.document_extraction_schemas:
        if normalized_id and _normalized(schema.document_class_id) == normalized_id:
            return schema
        if normalized_label and _normalized(schema.document_class) == normalized_label:
            return schema
    return None


def _payload_matches_schema(
    payload: dict[str, Any],
    schema: DocumentExtractionSchema,
    *,
    class_id: str | None,
    class_label: str | None,
) -> str | None:
    payload_schema_id = string(payload.get("schema_id"))
    payload_schema_name = string(payload.get("schema_name"))
    payload_class_id = string(payload.get("document_class_id"))
    payload_class_label = string(payload.get("document_class"))
    if payload_schema_id and payload_schema_id != schema.id:
        return "Extraction schema id does not match the current document class"
    if payload_schema_name and payload_schema_name != schema.name:
        return "Extraction schema name does not match the current document class"
    if payload_class_id and class_id and payload_class_id != class_id:
        return "Extraction class id does not match the current document class"
    if (
        payload_class_label
        and class_label
        and _normalized(payload_class_label) != _normalized(class_label)
    ):
        return "Extraction class label does not match the current document class"
    return None


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        normalized = value.strip().replace(".", "").replace(",", ".")
        try:
            return float(normalized)
        except ValueError:
            return None
    return None


def _coerce_string_value(value: Any) -> tuple[Any, list[str]]:
    return (value.strip() if isinstance(value, str) else str(value)), []


def _coerce_integer_value(value: Any) -> tuple[Any, list[str]]:
    if isinstance(value, int) and not isinstance(value, bool):
        return value, []
    number = _coerce_float(value)
    if number is not None and number.is_integer():
        return int(number), []
    return value, ["invalid_integer"]


def _coerce_number_value(value: Any) -> tuple[Any, list[str]]:
    number = _coerce_float(value)
    if number is not None:
        return number, []
    return value, ["invalid_number"]


def _coerce_boolean_value(value: Any) -> tuple[Any, list[str]]:
    if isinstance(value, bool):
        return value, []
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1", "ja"}:
            return True, []
        if normalized in {"false", "no", "0", "nein"}:
            return False, []
    return value, ["invalid_boolean"]


def _coerce_list_value(value: Any) -> tuple[Any, list[str]]:
    if isinstance(value, list):
        return [item for item in value if not value_is_empty(item)], []
    return [value], []


def _coerce_date_value(value: Any) -> tuple[Any, list[str]]:
    if isinstance(value, str):
        normalized = value.strip()
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(normalized, fmt).date().isoformat(), []
            except ValueError:
                continue
    return value, ["invalid_date"]


def _coerce_object_list_value(
    value: Any,
    *,
    field: DocumentExtractionField,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    if not isinstance(value, list):
        return [], [field.name], []

    coerced_items: list[dict[str, Any]] = []
    invalid_paths: list[str] = []
    missing_paths: list[str] = []
    for item_index, item in enumerate(value):
        if not isinstance(item, dict):
            invalid_paths.append(f"{field.name}[{item_index}]")
            continue
        coerced_item: dict[str, Any] = {}
        for child in field.fields:
            child_value, child_errors = _coerce_value(item.get(child.name), field=child)
            child_path = f"{field.name}[{item_index}].{child.name}"
            if value_is_empty(child_value):
                if child.required:
                    missing_paths.append(child_path)
                continue
            if child_errors:
                invalid_paths.append(child_path)
                continue
            coerced_item[child.name] = child_value
        if coerced_item:
            coerced_items.append(coerced_item)

    if field.required and not coerced_items:
        missing_paths.append(field.name)
    return coerced_items, invalid_paths, missing_paths


def _coerce_currency(value: Any) -> tuple[Any, list[str]]:
    if isinstance(value, dict):
        amount = _coerce_float(value.get("amount"))
        currency = value.get("currency")
        if amount is None:
            return value, ["invalid_currency"]
        if currency is not None:
            if not isinstance(currency, str) or len(currency.strip()) != 3:
                return value, ["invalid_currency"]
            currency = currency.strip().upper()
        return {"amount": amount, "currency": currency}, []
    if isinstance(value, int | float) and not isinstance(value, bool):
        return {"amount": float(value), "currency": None}, []
    if isinstance(value, str):
        normalized = value.strip()
        currency_match = re.search(r"\b([A-Z]{3})\b|([€$£])", normalized)
        raw_currency = (
            currency_match.group(1) or currency_match.group(2)
            if currency_match is not None
            else None
        )
        currency_map = {"€": "EUR", "$": "USD", "£": "GBP"}
        currency = currency_map.get(raw_currency or "", raw_currency)
        amount = _coerce_float(re.sub(r"[^0-9,.\-]", "", normalized))
        if amount is not None:
            return {"amount": amount, "currency": currency}, []
    return value, ["invalid_currency"]


_SCALAR_VALUE_COERCERS: dict[str, Callable[[Any], tuple[Any, list[str]]]] = {
    "str": _coerce_string_value,
    "int": _coerce_integer_value,
    "float": _coerce_number_value,
    "bool": _coerce_boolean_value,
    "list": _coerce_list_value,
    "date": _coerce_date_value,
}


def _coerce_value(
    value: Any, *, field: DocumentExtractionField
) -> tuple[Any, list[str]]:
    if value_is_empty(value):
        return None, []
    if field.dtype == "currency":
        return _coerce_currency(value)
    coercer = _SCALAR_VALUE_COERCERS.get(field.dtype)
    return coercer(value) if coercer is not None else (value, [])


def _field_payload(
    payload: dict[str, Any],
    field: DocumentExtractionField,
) -> dict[str, Any]:
    raw_fields = json_dict(payload.get("fields"))
    existing = json_dict(raw_fields.get(field.name))
    raw_data = json_dict(payload.get("data"))
    if "value" not in existing and field.name in raw_data:
        existing["value"] = raw_data[field.name]
    return existing


def _evidence_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _item_evidence_list(value: Any) -> list[list[Any]]:
    if not isinstance(value, list):
        return []
    return [entry if isinstance(entry, list) else [] for entry in value]


def _item_evidence_from_candidates(candidate_values: Any) -> list[list[Any]]:
    if not isinstance(candidate_values, list):
        return []
    item_evidence: list[list[Any]] = []
    for candidate in candidate_values:
        if not isinstance(candidate, dict):
            item_evidence.append([])
            continue
        item_evidence.append(_evidence_list(candidate.get("evidence")))
    return item_evidence


def _flatten_item_evidence(item_evidence: list[list[Any]]) -> list[Any]:
    evidence: list[Any] = []
    for entries in item_evidence:
        for entry in entries:
            if entry not in evidence:
                evidence.append(entry)
    return evidence


def _coerce_extraction_field_value(
    existing: dict[str, Any],
    field: DocumentExtractionField,
) -> tuple[Any, list[str], list[str]]:
    if field.dtype == "object_list":
        return _coerce_object_list_value(existing.get("value"), field=field)
    coerced_value, raw_validation_errors = _coerce_value(
        existing.get("value"),
        field=field,
    )
    validation_errors = [field.name] if raw_validation_errors else []
    return coerced_value, validation_errors, []


def _missing_required_field_names(
    *,
    field: DocumentExtractionField,
    coerced_value: Any,
    nested_missing_fields: list[str],
) -> list[str]:
    missing_fields = list(nested_missing_fields)
    if (
        value_is_empty(coerced_value)
        and field.required
        and field.name not in missing_fields
    ):
        missing_fields.append(field.name)
    return missing_fields


def _field_missing_reason(
    existing: dict[str, Any],
    *,
    field: DocumentExtractionField,
    coerced_value: Any,
) -> Any:
    if not value_is_empty(coerced_value):
        return None
    return existing.get("missing_reason") or (
        "missing_required" if field.required else "not_found"
    )


def _normalized_field_evidence(
    existing: dict[str, Any],
    field: DocumentExtractionField,
) -> tuple[list[Any], list[list[Any]], list[Any]]:
    candidate_values = existing.get("candidate_values")
    item_evidence = _item_evidence_list(existing.get("item_evidence"))
    if not item_evidence and field.dtype in {"list", "object_list"}:
        item_evidence = _item_evidence_from_candidates(candidate_values)
    evidence = _evidence_list(existing.get("evidence"))
    if not evidence and item_evidence:
        evidence = _flatten_item_evidence(item_evidence)
    normalized_candidates = (
        candidate_values if isinstance(candidate_values, list) else []
    )
    return evidence, item_evidence, normalized_candidates


def _validate_extraction_field(
    payload: dict[str, Any],
    field: DocumentExtractionField,
) -> _ValidatedExtractionField:
    existing = _field_payload(payload, field)
    coerced_value, validation_errors, nested_missing_fields = (
        _coerce_extraction_field_value(existing, field)
    )
    missing_required_fields = _missing_required_field_names(
        field=field,
        coerced_value=coerced_value,
        nested_missing_fields=nested_missing_fields,
    )
    evidence, item_evidence, candidate_values = _normalized_field_evidence(
        existing,
        field,
    )
    value_is_present = not value_is_empty(coerced_value)
    conflict = bool(existing.get("conflict", False))
    should_store_value = value_is_present and (
        not validation_errors or field.dtype == "object_list"
    )
    field_payload = {
        "value": coerced_value,
        "dtype": field.dtype,
        "required": field.required,
        "evidence": evidence,
        "item_evidence": item_evidence,
        "candidate_values": candidate_values,
        "conflict": conflict,
        "confidence": existing.get("confidence"),
        "validation_errors": validation_errors,
        "missing_reason": _field_missing_reason(
            existing,
            field=field,
            coerced_value=coerced_value,
        ),
    }
    return _ValidatedExtractionField(
        value=coerced_value,
        should_store_value=should_store_value,
        field_payload=field_payload,
        missing_required_fields=missing_required_fields,
        invalid_fields=validation_errors,
        conflicted=conflict,
        lacks_evidence=value_is_present and not evidence,
    )


def validate_extraction_payload(
    payload: dict[str, Any],
    *,
    settings: EffectiveAiSettings,
    class_id: str | None,
    class_label: str | None,
) -> ValidatedExtractionPayload:
    """Validate worker extraction output against the active class-owned schema."""
    status = _payload_status(payload)
    provider = string(payload.get("provider"))
    model = string(payload.get("model"))
    raw = dict(payload)
    schema = _schema_for_class(settings, class_id=class_id, class_label=class_label)
    payload_error = string(payload.get("error"))

    if schema is None:
        error = payload_error or "No extraction schema exists for the current class"
        return ValidatedExtractionPayload(
            status="skipped" if status != "failed" else "failed",
            provider=provider,
            model=model,
            schema_id=string(payload.get("schema_id")),
            schema_name=string(payload.get("schema_name")),
            schema_version=_schema_version(payload.get("schema_version")),
            class_id=string(payload.get("document_class_id")) or class_id,
            class_label=string(payload.get("document_class")) or class_label,
            data={},
            fields={},
            summary=json_dict(payload.get("summary")),
            raw=raw,
            error=error,
            trusted=False,
        )

    summary = json_dict(payload.get("summary"))
    schema_error = _payload_matches_schema(
        payload,
        schema,
        class_id=class_id,
        class_label=class_label,
    )
    if status != "completed" or schema_error is not None:
        return ValidatedExtractionPayload(
            status="failed" if schema_error is not None else status,
            provider=provider,
            model=model,
            schema_id=schema.id,
            schema_name=schema.name,
            schema_version=schema.version,
            class_id=schema.document_class_id or class_id,
            class_label=schema.document_class or class_label,
            data={},
            fields={},
            summary=summary,
            raw=raw,
            error=schema_error or payload_error,
            trusted=False,
        )

    data: dict[str, Any] = {}
    fields: dict[str, dict[str, Any]] = {}
    missing_required_fields: list[str] = []
    invalid_fields: list[str] = []
    conflicted_fields: list[str] = []
    fields_without_evidence: list[str] = []

    for field in schema.fields:
        validated_field = _validate_extraction_field(payload, field)
        missing_required_fields.extend(validated_field.missing_required_fields)
        invalid_fields.extend(validated_field.invalid_fields)
        if validated_field.conflicted:
            conflicted_fields.append(field.name)
        if validated_field.lacks_evidence:
            fields_without_evidence.append(field.name)
        if validated_field.should_store_value:
            data[field.name] = validated_field.value
        fields[field.name] = validated_field.field_payload

    summary.update(
        {
            "missing_required_fields": missing_required_fields,
            "invalid_fields": invalid_fields,
            "conflicted_fields": conflicted_fields,
            "fields_without_evidence": fields_without_evidence,
            "fields_with_evidence": sum(
                1
                for field_payload in fields.values()
                if isinstance(field_payload.get("evidence"), list)
                and field_payload["evidence"]
            ),
            "needs_review": bool(
                missing_required_fields
                or invalid_fields
                or conflicted_fields
                or fields_without_evidence
            ),
        }
    )
    return ValidatedExtractionPayload(
        status="completed",
        provider=provider,
        model=model,
        schema_id=schema.id,
        schema_name=schema.name,
        schema_version=schema.version,
        class_id=schema.document_class_id or class_id,
        class_label=schema.document_class or class_label,
        data=data,
        fields=fields,
        summary=summary,
        raw=raw,
        error=None,
        trusted=True,
    )
