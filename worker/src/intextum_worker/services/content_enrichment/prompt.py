"""Prompt construction helpers for chat extraction."""

from __future__ import annotations

import json

from intextum_worker.models import (
    WorkerDocumentExtractionField,
    WorkerDocumentExtractionSchema,
)
from intextum_worker.services.content_enrichment_utils import _value_is_empty

from .evidence_grounding import _short_anchor


def _field_signature(field: WorkerDocumentExtractionField) -> str:
    if field.dtype == "object_list":
        children = ", ".join(f"{child.name}:{child.dtype}" for child in field.fields)
        return f"{field.name} (object_list of {{{children}}})"
    return f"{field.name} ({field.dtype})"


def _render_schema_block(
    schema: WorkerDocumentExtractionSchema,
    target_field_names: list[str],
) -> str:
    """Render the schema description used in the user prompt."""
    lines: list[str] = []
    for field in schema.fields:
        if field.name not in target_field_names:
            continue
        header = f'- field_name: "{field.name}"'
        body = [
            header,
            f"  type: {field.dtype}",
            f"  required: {str(field.required).lower()}",
            f"  description: {field.description}",
        ]
        if field.dtype == "object_list" and field.fields:
            body.append("  child_fields:")
            for child in field.fields:
                body.append(f"    - {child.name} ({child.dtype}): {child.description}")
        lines.append("\n".join(body))
    return "\n\n".join(lines)


def _render_examples_block(
    schema: WorkerDocumentExtractionSchema,
    target_field_names: list[str],
) -> str:
    """Render a few-shot block from per-field examples and scenes."""
    blocks: list[str] = []
    for field in schema.fields:
        if field.name not in target_field_names:
            continue
        for example in field.examples:
            if _value_is_empty(example.value):
                continue
            example_anchor_source = (example.extraction_text or "").strip() or (
                str(example.value).strip()
                if not isinstance(example.value, dict)
                else ""
            )
            entry = {
                "field": field.name,
                "value": example.value,
                "evidence_anchor": _short_anchor(example_anchor_source),
                "source_excerpt": example.text,
            }
            blocks.append(json.dumps(entry, ensure_ascii=False, indent=2))
    target_names_set = set(target_field_names)
    for scene in getattr(schema, "scenes", []) or []:
        scene_entries = []
        for scene_extraction in scene.extractions:
            if scene_extraction.field not in target_names_set:
                continue
            if _value_is_empty(scene_extraction.value):
                continue
            scene_entries.append(
                {
                    "field": scene_extraction.field,
                    "value": scene_extraction.value,
                    "evidence_anchor": _short_anchor(
                        scene_extraction.extraction_text.strip()
                    ),
                }
            )
        if not scene_entries:
            continue
        blocks.append(
            json.dumps(
                {"source_excerpt": scene.text, "extractions": scene_entries},
                ensure_ascii=False,
                indent=2,
            )
        )
    if not blocks:
        return ""
    return "EXAMPLES:\n" + "\n\n---\n\n".join(blocks)


def _expected_json_shape(
    schema: WorkerDocumentExtractionSchema,
    target_field_names: list[str],
) -> str:
    """Describe the expected JSON response shape for the user prompt."""
    parts = []
    for field in schema.fields:
        if field.name not in target_field_names:
            continue
        if field.dtype == "object_list":
            child_shape = ", ".join(
                f'"{child.name}": <{child.dtype} or null>' for child in field.fields
            )
            parts.append(
                f'  "{field.name}": ['
                f' {{"value": {{{child_shape}}}, '
                f'"evidence_anchor": "<short prefix or null>"}}'
                f", ... ]"
            )
        elif field.dtype == "list":
            parts.append(f'  "{field.name}": [ "<one verbatim list item>", ... ]')
        else:
            parts.append(
                f'  "{field.name}":'
                f' {{"value": <{field.dtype} or null>, '
                f'"evidence_anchor": "<short prefix or null>"}}'
            )
    return "{\n" + ",\n".join(parts) + "\n}"


def _build_prompt(
    *,
    schema: WorkerDocumentExtractionSchema,
    document_class: str | None,
    target_field_names: list[str],
    selected_text: str,
    retry_hint: str | None = None,
) -> tuple[str, str]:
    """Build (system_message, user_message) for one extraction pass."""
    schema_block = _render_schema_block(schema, target_field_names)
    examples_block = _render_examples_block(schema, target_field_names)
    shape_block = _expected_json_shape(schema, target_field_names)

    field_signatures = ", ".join(
        _field_signature(field)
        for field in schema.fields
        if field.name in target_field_names
    )

    system_message = (
        "You are a structured-extraction assistant. You read a source document and "
        "return JSON describing every value asked for, plus a short verbatim "
        "anchor from the source that locates the value. You never invent values. "
        "Anchors are short (at most ten words) and copied character-for-character "
        "from the source."
    )

    user_message_parts = [
        f"DOCUMENT CLASS: {document_class or schema.document_class or 'unknown'}",
        f"SCHEMA: {schema.name}",
        f"FIELDS TO EXTRACT: {field_signatures}",
        "",
        "FIELD DETAILS:",
        schema_block,
    ]
    if examples_block:
        user_message_parts.extend(["", examples_block])
    user_message_parts.extend(
        [
            "",
            "INSTRUCTIONS:",
            "1. Extract every configured field from the SOURCE TEXT below.",
            '2. For each scalar value return {"value": ..., "evidence_anchor": "..."}.',
            "If a scalar field is absent, return "
            '{"value": null, "evidence_anchor": null}.',
            "3. For each object_list field return an array of objects with "
            '{"value": ..., "evidence_anchor": "..."}.',
            "If an object_list field is absent, return an empty array []. Include "
            "every configured child key in each value object; use null for missing "
            "child values.",
            "4. For each plain list field return only an array of strings. Each "
            "string must be one complete verbatim list item from the source. Do "
            "not wrap list items in objects. Do not add evidence anchors for "
            "plain list fields. If a plain list field is absent, return an empty "
            "array [].",
            "5. `evidence_anchor` MUST be a verbatim character-for-character substring "
            "of the SOURCE TEXT, at most ten words long. Use the shortest unique "
            "prefix of the source span the value comes from. Do not paraphrase.",
            "6. Keep `evidence_anchor` short - never copy the whole value text into "
            "the anchor. The anchor is only a position marker.",
            "7. Always return every requested top-level field. Do not invent "
            "placeholders such as N/A, unknown, or empty strings.",
            "8. Only extract values that match the field semantics. Do not extract "
            "section headings, table of contents entries, addresses, or unrelated "
            "numbered lists.",
            "9. For list fields, extract only entries from the matching section. "
            "If a new section, legal remedy, fee, reasoning, signature, or attachment "
            "area starts, stop extracting list entries.",
            "10. Keep the response compact. Never repeat SOURCE TEXT outside JSON. "
            "Never add explanations, markdown, comments, or duplicate list entries.",
            "",
            "EXPECTED JSON SHAPE:",
            shape_block,
        ]
    )
    if retry_hint:
        user_message_parts.extend(["", "RETRY NOTE:", retry_hint])
    user_message_parts.extend(
        [
            "",
            "SOURCE TEXT:",
            selected_text,
            "",
            "Respond with a single JSON object matching the expected shape.",
        ]
    )
    return system_message, "\n".join(user_message_parts)
