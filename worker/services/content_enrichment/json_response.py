"""JSON response-format helpers for chat extraction."""

from __future__ import annotations

import json
import re
from hashlib import sha1
from typing import Any

from models import (
    WorkerDocumentExtractionField,
    WorkerDocumentExtractionSchema,
)

_JSON_SCHEMA_NAME_RE = re.compile(r"[^A-Za-z0-9_-]+")

_JSON_OBJECT_RESPONSE_FORMAT: dict[str, Any] = {"type": "json_object"}


class JsonSchemaUnsupportedError(RuntimeError):
    """Raised when the configured chat backend rejects json_schema mode."""


def _looks_like_json_schema_unsupported(text: str) -> bool:
    normalized = text.casefold()
    if not any(
        marker in normalized
        for marker in ("json_schema", "response_format", "structured output")
    ):
        return False
    return any(
        marker in normalized
        for marker in (
            "unsupported",
            "not supported",
            "does not support",
            "not implemented",
            "unknown response_format",
            "unknown parameter",
            "unrecognized",
            "not a valid response_format",
            "invalid value: 'json_schema'",
            'invalid value: "json_schema"',
        )
    )


def _error_message_from_payload(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, str):
        return error
    if isinstance(error, dict):
        message = error.get("message") or error.get("detail")
        if isinstance(message, str):
            return message
    detail = payload.get("detail")
    if isinstance(detail, str):
        return detail
    return None


def _json_schema_unsupported_message_from_text(text: str) -> str | None:
    stripped = text.strip()
    if not stripped.startswith("{"):
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    message = _error_message_from_payload(payload)
    if message and _looks_like_json_schema_unsupported(message):
        return message
    return None


def _raise_if_json_schema_unsupported_error(exc: Exception) -> None:
    message = str(exc) or repr(exc)
    if _looks_like_json_schema_unsupported(message):
        raise JsonSchemaUnsupportedError(message) from exc


def _strict_object_schema(properties: dict[str, Any]) -> dict[str, Any]:
    """Return the strict object shape required by structured-output backends."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties.keys()),
        "additionalProperties": False,
    }


def _nullable_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Allow ``null`` for a simple typed schema while preserving constraints."""
    nullable = dict(schema)
    schema_type = nullable.get("type")
    if isinstance(schema_type, str):
        nullable["type"] = [schema_type, "null"]
    elif isinstance(schema_type, list) and "null" not in schema_type:
        nullable["type"] = [*schema_type, "null"]
    return nullable


def _currency_value_schema() -> dict[str, Any]:
    return _strict_object_schema(
        {
            "amount": {"type": ["number", "null"]},
            "currency": {"type": ["string", "null"]},
        }
    )


def _field_value_json_schema(dtype: str, *, nullable: bool = True) -> dict[str, Any]:
    if dtype in {"str", "date"}:
        schema: dict[str, Any] = {"type": "string"}
    elif dtype == "int":
        schema = {"type": "integer"}
    elif dtype == "float":
        schema = {"type": "number"}
    elif dtype == "bool":
        schema = {"type": "boolean"}
    elif dtype == "currency":
        schema = _currency_value_schema()
    elif dtype == "list":
        schema = {"type": "array", "items": {"type": "string"}}
    else:
        schema = {"type": "string"}
    return _nullable_schema(schema) if nullable else schema


def _field_response_json_schema(field: WorkerDocumentExtractionField) -> dict[str, Any]:
    if field.dtype == "list":
        return {"type": "array", "items": {"type": "string"}}
    if field.dtype == "object_list":
        child_properties = {
            child.name: _field_value_json_schema(child.dtype, nullable=True)
            for child in field.fields
        }
        return {
            "type": "array",
            "items": _strict_object_schema(
                {
                    "value": _strict_object_schema(child_properties),
                    "evidence_anchor": {"type": ["string", "null"]},
                }
            ),
        }
    return _strict_object_schema(
        {
            "value": _field_value_json_schema(field.dtype, nullable=True),
            "evidence_anchor": {"type": ["string", "null"]},
        }
    )


def _json_schema_response_name(
    schema: WorkerDocumentExtractionSchema,
    target_field_names: list[str],
) -> str:
    raw = "_".join([schema.name or "document_extraction", *target_field_names])
    normalized = _JSON_SCHEMA_NAME_RE.sub("_", raw).strip("_")
    if not normalized:
        normalized = "document_extraction"
    digest = sha1(raw.encode("utf-8")).hexdigest()[:8]
    prefix = normalized[:55].rstrip("_-") or "document_extraction"
    return f"{prefix}_{digest}"


def _json_schema_response_format_for_batch(
    schema: WorkerDocumentExtractionSchema,
    target_field_names: list[str],
) -> dict[str, Any]:
    """Compile the extraction batch into OpenAI-compatible strict JSON schema."""
    target_set = set(target_field_names)
    properties = {
        field.name: _field_response_json_schema(field)
        for field in schema.fields
        if field.name in target_set
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": _json_schema_response_name(schema, target_field_names),
            "strict": True,
            "schema": _strict_object_schema(properties),
        },
    }
