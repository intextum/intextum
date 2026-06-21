"""Pure helper utilities for worker-side content enrichment."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import date, datetime
from typing import Any

from intextum_worker.models import (
    WorkerDocumentEvidence,
    WorkerDocumentExtractionFieldResult,
    WorkerDocumentExtractionSchema,
)

MAX_EXTRACTION_WINDOWS = 24
MAX_SELECTED_EXTRACTION_CHUNKS = 40
MAX_EXTRACTION_WINDOW_CHARS = 1_600
MAX_EVIDENCE_TEXT_CHARS = 1_600
MAX_EVIDENCE_SNIPPET_CHARS = 240
MAX_FIELD_EVIDENCE = 3
MIN_SCALAR_CONFLICT_SUPPORT = 2
_MISSING_VALUE_PLACEHOLDERS = {
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


def _normalize_text(text: str, *, max_chars: int) -> str:
    """Normalize document text into a compact single-line-per-paragraph string."""
    compact = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    return compact[:max_chars].strip()


def _compact_blank_lines(text: str) -> str:
    """Trim trailing whitespace on each line and collapse runs of 3+ blank lines."""
    if not isinstance(text, str) or not text:
        return ""
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned: list[str] = []
    blank_run = 0
    for line in lines:
        if line.strip():
            cleaned.append(line)
            blank_run = 0
        else:
            blank_run += 1
            if blank_run <= 1:
                cleaned.append("")
    while cleaned and not cleaned[0]:
        cleaned.pop(0)
    while cleaned and not cleaned[-1]:
        cleaned.pop()
    return "\n".join(cleaned)


def _chunk_str_list_attr(chunk: Any, attr: str) -> list[str]:
    """Read a list[str] attribute either directly off the chunk or from chunk.meta."""
    direct = getattr(chunk, attr, None)
    if isinstance(direct, list) and direct:
        return [value for value in direct if isinstance(value, str) and value.strip()]
    meta = getattr(chunk, "meta", None)
    if meta is not None:
        meta_value = getattr(meta, attr, None)
        if isinstance(meta_value, list) and meta_value:
            return [
                value
                for value in meta_value
                if isinstance(value, str) and value.strip()
            ]
    return []


def _is_docling_table_item(item: Any) -> bool:
    """Best-effort check for a Docling TableItem instance without forcing the import."""
    try:  # pylint: disable=import-outside-toplevel
        from docling_core.types.doc.document import TableItem
    except ImportError:
        return False
    if not isinstance(TableItem, type):
        return False
    try:
        return isinstance(item, TableItem)
    except TypeError:
        return False


def _render_table_item_as_markdown(item: Any) -> str | None:
    """Render a Docling TableItem as markdown (or HTML fallback) for the extractor."""
    if not _is_docling_table_item(item):
        return None
    dataframe_method = getattr(item, "export_to_dataframe", None)
    if callable(dataframe_method):
        try:
            dataframe = dataframe_method()
        except Exception:  # pylint: disable=broad-exception-caught
            dataframe = None
        if dataframe is not None and hasattr(dataframe, "to_markdown"):
            try:
                rendered = dataframe.to_markdown(index=False)
            except Exception:  # pylint: disable=broad-exception-caught
                rendered = None
            if isinstance(rendered, str) and rendered.strip():
                return rendered.strip()
    html_method = getattr(item, "export_to_html", None)
    if callable(html_method):
        try:
            rendered_html = html_method()
        except Exception:  # pylint: disable=broad-exception-caught
            rendered_html = None
        if isinstance(rendered_html, str) and rendered_html.strip():
            return rendered_html.strip()
    return None


def _chunk_tables_as_markdown(chunk: Any) -> list[str]:
    """Collect markdown renderings of any Docling TableItems inside a chunk's metadata."""
    meta = getattr(chunk, "meta", None)
    if meta is None:
        return []
    doc_items = getattr(meta, "doc_items", None)
    if not doc_items:
        return []
    tables: list[str] = []
    for item in doc_items:
        rendered = _render_table_item_as_markdown(item)
        if rendered:
            tables.append(rendered)
    return tables


def _extraction_window_text(
    chunk: Any,
    *,
    max_chars: int,
) -> str:
    """Build the text fed to the extractor for one chunk, preserving Docling layout."""
    body = getattr(chunk, "text", "")
    if not isinstance(body, str):
        body = ""
    body = body.strip()

    headings = _chunk_str_list_attr(chunk, "headings")
    captions = _chunk_str_list_attr(chunk, "captions")
    tables = _chunk_tables_as_markdown(chunk)

    blocks: list[str] = []
    if headings:
        blocks.append("\n".join(headings))
    if captions:
        blocks.append("\n".join(captions))
    blocks.extend(tables)
    if body:
        blocks.append(body)

    if not blocks:
        return ""

    combined = _compact_blank_lines("\n\n".join(blocks))
    if max_chars <= 0 or len(combined) <= max_chars:
        return combined
    return combined[:max_chars].rstrip()


def _pick_schema(
    schemas: list[WorkerDocumentExtractionSchema],
    *,
    document_class: str | None,
    document_class_id: str | None = None,
) -> WorkerDocumentExtractionSchema | None:
    if document_class_id:
        normalized_document_class_id = document_class_id.strip().lower()
        if normalized_document_class_id:
            for schema in schemas:
                if (
                    schema.document_class_id.strip().lower()
                    == normalized_document_class_id
                ):
                    return schema
    if document_class:
        normalized_document_class = document_class.strip().lower()
        for schema in schemas:
            if schema.document_class.strip().lower() == normalized_document_class:
                return schema
    return None


def _clip_text(value: str, *, max_chars: int) -> str:
    normalized = value.strip()
    if len(normalized) <= max_chars:
        return normalized
    if max_chars <= 3:
        return normalized[:max_chars]
    return normalized[: max_chars - 3].rstrip() + "..."


def _page_numbers_from_chunk(chunk: Any) -> list[int]:
    direct_page_numbers = getattr(chunk, "page_numbers", None)
    if isinstance(direct_page_numbers, list) and direct_page_numbers:
        return [value for value in direct_page_numbers if isinstance(value, int)]
    meta = getattr(chunk, "meta", None)
    page_numbers: set[int] = set()
    if not meta or not getattr(meta, "doc_items", None):
        return []

    for doc_item in meta.doc_items:
        if hasattr(doc_item, "prov") and doc_item.prov:
            for prov in doc_item.prov:
                page_no = getattr(prov, "page_no", None)
                if isinstance(page_no, int):
                    page_numbers.add(page_no)
    return sorted(page_numbers)


def _doc_refs_from_chunk(chunk: Any) -> list[str]:
    direct_doc_refs = getattr(chunk, "doc_refs", None)
    if isinstance(direct_doc_refs, list) and direct_doc_refs:
        return [value for value in direct_doc_refs if isinstance(value, str) and value]
    meta = getattr(chunk, "meta", None)
    if not meta or not getattr(meta, "doc_items", None):
        return []

    refs: list[str] = []
    for doc_item in meta.doc_items:
        self_ref = getattr(doc_item, "self_ref", None)
        if isinstance(self_ref, str) and self_ref and self_ref not in refs:
            refs.append(self_ref)
    return refs


def _images_from_chunk(chunk: Any) -> list[str]:
    direct_images = getattr(chunk, "images", None)
    if isinstance(direct_images, list) and direct_images:
        return [value for value in direct_images if isinstance(value, str) and value]
    meta = getattr(chunk, "meta", None)
    if not meta or not getattr(meta, "doc_items", None):
        return []

    images: list[str] = []
    for doc_item in meta.doc_items:
        image = getattr(doc_item, "image", None)
        uri = getattr(image, "uri", None)
        if isinstance(uri, str) and uri and uri not in images:
            images.append(uri)
    return images


def _chunk_index_from_chunk(chunk: Any, fallback: int) -> int:
    direct_chunk_index = getattr(chunk, "chunk_index", None)
    if isinstance(direct_chunk_index, int):
        return direct_chunk_index
    return fallback


def _build_chunk_evidence(
    chunk: Any, chunk_index: int
) -> WorkerDocumentEvidence | None:
    text = getattr(chunk, "text", None)
    if not isinstance(text, str) or not text.strip():
        return None
    normalized = _normalize_text(text, max_chars=MAX_EVIDENCE_TEXT_CHARS)
    if not normalized:
        return None
    return WorkerDocumentEvidence(
        chunk_index=chunk_index,
        page_numbers=_page_numbers_from_chunk(chunk),
        doc_refs=_doc_refs_from_chunk(chunk),
        images=_images_from_chunk(chunk),
        snippet=_clip_text(normalized, max_chars=MAX_EVIDENCE_SNIPPET_CHARS),
        score=_numeric_confidence(getattr(chunk, "score", None)),
        matched_queries=[
            value
            for value in getattr(chunk, "matched_queries", [])
            if isinstance(value, str) and value
        ],
        source=getattr(chunk, "source", None)
        if isinstance(getattr(chunk, "source", None), str)
        else None,
    )


def _build_text_evidence(text: str) -> WorkerDocumentEvidence | None:
    normalized = _normalize_text(text, max_chars=MAX_EVIDENCE_TEXT_CHARS)
    if not normalized:
        return None
    return WorkerDocumentEvidence(
        chunk_index=None,
        page_numbers=[],
        doc_refs=[],
        images=[],
        snippet=_clip_text(normalized, max_chars=MAX_EVIDENCE_SNIPPET_CHARS),
    )


def _iter_extraction_windows(
    chunks: list[Any] | None,
    *,
    fallback_text: str,
    max_windows: int = MAX_EXTRACTION_WINDOWS,
    max_chars: int = MAX_EXTRACTION_WINDOW_CHARS,
) -> list[tuple[str, WorkerDocumentEvidence | None]]:
    windows: list[tuple[str, WorkerDocumentEvidence | None]] = []
    if chunks:
        for fallback_chunk_index, chunk in enumerate(chunks):
            text = getattr(chunk, "text", None)
            if not isinstance(text, str) or not text.strip():
                continue
            window_text = _extraction_window_text(chunk, max_chars=max_chars)
            if not window_text:
                continue
            chunk_index = _chunk_index_from_chunk(chunk, fallback_chunk_index)
            windows.append((window_text, _build_chunk_evidence(chunk, chunk_index)))
            if len(windows) >= max_windows:
                break
    if windows:
        return windows

    normalized_fallback = _normalize_text(fallback_text, max_chars=max_chars)
    if not normalized_fallback:
        return []
    return [(normalized_fallback, _build_text_evidence(normalized_fallback))]


def _evidence_payloads(
    evidence_items: list[WorkerDocumentEvidence],
) -> list[dict[str, Any]]:
    """Serialize evidence for candidate metadata."""
    return [
        evidence.model_dump(mode="json", exclude_none=True)
        for evidence in evidence_items[:MAX_FIELD_EVIDENCE]
    ]


def _candidate_source_score(
    evidence_items: list[WorkerDocumentEvidence],
) -> float | None:
    scores = [
        evidence.score
        for evidence in evidence_items
        if evidence.score is not None and math.isfinite(evidence.score)
    ]
    return max(scores) if scores else None


def _candidate_source_query_keys(
    evidence_items: list[WorkerDocumentEvidence],
) -> list[str]:
    keys: list[str] = []
    for evidence in evidence_items:
        for key in evidence.matched_queries:
            if key not in keys:
                keys.append(key)
    return keys


def _candidate_payload(
    *,
    value: Any,
    confidence: float | None,
    evidence: list[WorkerDocumentEvidence],
    span: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Build UI/debug metadata for one extracted candidate value."""
    payload: dict[str, Any] = {
        "value": value,
        "evidence": _evidence_payloads(evidence),
    }
    if confidence is not None:
        payload["confidence"] = confidence
    source_score = _candidate_source_score(evidence)
    if source_score is not None:
        payload["source_score"] = source_score
    source_query_keys = _candidate_source_query_keys(evidence)
    if source_query_keys:
        payload["source_query_keys"] = source_query_keys
    if span is not None:
        payload["span"] = span
    return payload


def _normalized_search_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def _search_terms_for_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, bool):
        return ["true" if value else "false"]
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, str):
        normalized = _normalized_search_text(value)
        return [normalized] if normalized else []
    if isinstance(value, list):
        terms: list[str] = []
        for item in value:
            terms.extend(_search_terms_for_value(item))
        return terms
    if isinstance(value, dict):
        terms = []
        for item in value.values():
            terms.extend(_search_terms_for_value(item))
        return terms
    return []


def _find_local_evidence_for_terms(
    chunks: list[Any] | None,
    terms: list[str],
    *,
    max_items: int = MAX_FIELD_EVIDENCE,
) -> list[WorkerDocumentEvidence]:
    if not chunks:
        return []

    normalized_terms = []
    for term in terms:
        normalized = _normalized_search_text(term)
        if normalized and normalized not in normalized_terms:
            normalized_terms.append(normalized)
    if not normalized_terms:
        return []

    evidence_items: list[WorkerDocumentEvidence] = []
    for chunk_index, chunk in enumerate(chunks):
        text = getattr(chunk, "text", None)
        if not isinstance(text, str) or not text.strip():
            continue
        normalized_chunk_text = _normalized_search_text(text)
        if not any(term in normalized_chunk_text for term in normalized_terms):
            continue
        evidence = _build_chunk_evidence(chunk, chunk_index)
        if evidence is None:
            continue
        evidence_items.append(evidence)
        if len(evidence_items) >= max_items:
            break
    return evidence_items


def _find_local_evidence_for_value(
    chunks: list[Any] | None,
    value: Any,
    *,
    max_items: int = MAX_FIELD_EVIDENCE,
) -> list[WorkerDocumentEvidence]:
    return _find_local_evidence_for_terms(
        chunks,
        _search_terms_for_value(value),
        max_items=max_items,
    )


def _resolve_classification_label(raw_output: Any) -> str | None:
    if not isinstance(raw_output, dict):
        return None
    raw_label = raw_output.get("document_class")
    if isinstance(raw_label, str) and raw_label.strip():
        return raw_label.strip()
    if isinstance(raw_label, dict):
        return _classification_candidate_label(raw_label)
    if isinstance(raw_label, list):
        return _best_classification_candidate_label(raw_label)
    return None


def _classification_candidate_label(candidate: dict[str, Any]) -> str | None:
    for key in ("label", "class", "class_name", "name", "value", "text"):
        value = candidate.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _numeric_confidence(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        score = float(value)
        return score if math.isfinite(score) else None
    if isinstance(value, str):
        try:
            score = float(value.strip())
        except ValueError:
            return None
        return score if math.isfinite(score) else None
    return None


def _classification_candidate_confidence(candidate: dict[str, Any]) -> float | None:
    for key in ("confidence", "score", "probability", "prob"):
        confidence = _numeric_confidence(candidate.get(key))
        if confidence is not None:
            return confidence
    return None


def _best_classification_candidate_label(candidates: list[Any]) -> str | None:
    best_label = None
    best_score = float("-inf")
    fallback_label = None
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        label = _classification_candidate_label(candidate)
        if label is None:
            continue
        if fallback_label is None:
            fallback_label = label
        confidence = _classification_candidate_confidence(candidate)
        if confidence is not None and confidence > best_score:
            best_score = confidence
            best_label = label
    return best_label or fallback_label


def _resolve_classification_confidence(
    raw_output: Any,
    *,
    label: str | None = None,
) -> float | None:
    """Extract a model confidence score from known GLiNER2 result shapes."""
    if not isinstance(raw_output, dict):
        return None

    for key in (
        "confidence",
        "score",
        "probability",
        "prob",
        "document_class_confidence",
        "document_class_score",
        "document_class_probability",
    ):
        confidence = _numeric_confidence(raw_output.get(key))
        if confidence is not None:
            return confidence

    normalized_label = label.strip().lower() if isinstance(label, str) else None
    for key in ("scores", "confidences", "probabilities", "confidence_by_label"):
        score_map = raw_output.get(key)
        if not isinstance(score_map, dict):
            continue
        if normalized_label is not None:
            for candidate_label, candidate_score in score_map.items():
                if (
                    isinstance(candidate_label, str)
                    and candidate_label.strip().lower() == normalized_label
                ):
                    confidence = _numeric_confidence(candidate_score)
                    if confidence is not None:
                        return confidence
        scored_values = [
            confidence
            for confidence in (
                _numeric_confidence(value) for value in score_map.values()
            )
            if confidence is not None
        ]
        if scored_values:
            return max(scored_values)

    raw_label = raw_output.get("document_class")
    if isinstance(raw_label, dict):
        return _classification_candidate_confidence(raw_label)
    if isinstance(raw_label, list):
        best_score = None
        for candidate in raw_label:
            if not isinstance(candidate, dict):
                continue
            candidate_label = _classification_candidate_label(candidate)
            confidence = _classification_candidate_confidence(candidate)
            if confidence is None:
                continue
            if (
                normalized_label is not None
                and isinstance(candidate_label, str)
                and candidate_label.strip().lower() == normalized_label
            ):
                return confidence
            if best_score is None or confidence > best_score:
                best_score = confidence
        return best_score

    return None


def _field_key(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value.strip().lower()
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _coerce_field_value(value: Any, *, dtype: str) -> Any:
    if _value_is_empty(value):
        return [] if dtype == "list" else None
    if dtype == "list":
        if isinstance(value, list):
            return [item for item in value if not _value_is_empty(item)]
        return [value] if not _value_is_empty(value) else []
    if dtype == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "yes", "1", "ja"}:
                return True
            if normalized in {"false", "no", "0", "nein"}:
                return False
        return value
    if dtype == "int":
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError:
                return value.strip()
        return value
    if dtype == "float":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            normalized = value.strip().replace(".", "").replace(",", ".")
            try:
                return float(normalized)
            except ValueError:
                return value.strip()
        return value
    if dtype == "date":
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, str):
            normalized = value.strip()
            for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
                try:
                    return datetime.strptime(normalized, fmt).date().isoformat()
                except ValueError:
                    continue
            return normalized
        return value
    if dtype == "currency":
        if isinstance(value, dict):
            amount = value.get("amount")
            currency = value.get("currency")
            coerced_amount = _coerce_field_value(amount, dtype="float")
            if isinstance(coerced_amount, int | float) and not isinstance(
                coerced_amount, bool
            ):
                return {
                    "amount": float(coerced_amount),
                    "currency": currency.strip().upper()
                    if isinstance(currency, str) and currency.strip()
                    else None,
                }
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return {"amount": float(value), "currency": None}
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
            numeric_part = re.sub(r"[^0-9,.\-]", "", normalized)
            amount = _coerce_field_value(numeric_part, dtype="float")
            if isinstance(amount, int | float) and not isinstance(amount, bool):
                return {"amount": float(amount), "currency": currency}
            return normalized
        return value
    if isinstance(value, str):
        return value.strip()
    return value


def _field_validation_errors(value: Any, *, dtype: str) -> list[str]:
    if _value_is_empty(value):
        return []
    if dtype == "str":
        return [] if isinstance(value, str) else ["invalid_string"]
    if dtype == "int":
        return (
            []
            if isinstance(value, int) and not isinstance(value, bool)
            else ["invalid_integer"]
        )
    if dtype == "float":
        return (
            []
            if isinstance(value, int | float) and not isinstance(value, bool)
            else ["invalid_number"]
        )
    if dtype == "bool":
        return [] if isinstance(value, bool) else ["invalid_boolean"]
    if dtype == "list":
        return [] if isinstance(value, list) else ["invalid_list"]
    if dtype == "date":
        if isinstance(value, str):
            try:
                datetime.strptime(value, "%Y-%m-%d")
                return []
            except ValueError:
                return ["invalid_date"]
        return ["invalid_date"]
    if dtype == "currency":
        if (
            isinstance(value, dict)
            and isinstance(value.get("amount"), int | float)
            and not isinstance(value.get("amount"), bool)
            and (
                value.get("currency") is None
                or (
                    isinstance(value.get("currency"), str)
                    and len(value["currency"]) == 3
                )
            )
        ):
            return []
        return ["invalid_currency"]
    return []


def _value_is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        normalized = _normalized_search_text(value)
        return not normalized or normalized in _MISSING_VALUE_PLACEHOLDERS
    if isinstance(value, list):
        return len(value) == 0
    if isinstance(value, dict):
        return len(value) == 0
    return False


def _iter_extracted_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _select_scalar_field_result(
    values: list[tuple[Any, WorkerDocumentEvidence | None, float | None]],
    *,
    dtype: str,
    required: bool,
) -> WorkerDocumentExtractionFieldResult | None:
    if not values:
        return None

    key_counts = Counter(
        field_key
        for value, _evidence, _confidence in values
        if (field_key := _field_key(value))
    )
    selected_key = next(
        (field_key for field_key, _count in key_counts.most_common() if field_key),
        "",
    )
    if not selected_key:
        return None

    selected_value = next(
        value
        for value, _evidence, _confidence in values
        if _field_key(value) == selected_key
    )
    evidence = [
        evidence
        for value, evidence, _confidence in values
        if _field_key(value) == selected_key and evidence is not None
    ][:MAX_FIELD_EVIDENCE]
    confidences = [
        confidence
        for value, _evidence, confidence in values
        if _field_key(value) == selected_key and confidence is not None
    ]
    candidate_values = []
    for field_key in key_counts:
        candidate_evidence = [
            evidence
            for value, evidence, _confidence in values
            if _field_key(value) == field_key and evidence is not None
        ][:MAX_FIELD_EVIDENCE]
        candidate_confidences = [
            confidence
            for value, _evidence, confidence in values
            if _field_key(value) == field_key and confidence is not None
        ]
        candidate_value = next(
            value
            for value, _evidence, _confidence in values
            if _field_key(value) == field_key
        )
        candidate_values.append(
            _candidate_payload(
                value=candidate_value,
                confidence=max(candidate_confidences)
                if candidate_confidences
                else None,
                evidence=candidate_evidence,
            )
        )

    return WorkerDocumentExtractionFieldResult(
        value=selected_value,
        dtype=dtype,
        required=required,
        evidence=evidence,
        candidate_values=candidate_values,
        confidence=max(confidences) if confidences else None,
        conflict=sum(
            1 for count in key_counts.values() if count >= MIN_SCALAR_CONFLICT_SUPPORT
        )
        > 1,
        validation_errors=_field_validation_errors(selected_value, dtype=dtype),
    )


def _select_list_field_result(
    values: list[tuple[Any, WorkerDocumentEvidence | None, float | None]],
    *,
    required: bool,
) -> WorkerDocumentExtractionFieldResult | None:
    flattened: list[Any] = []
    evidence: list[WorkerDocumentEvidence] = []
    confidences: list[float] = []
    candidates_by_key: dict[str, dict[str, Any]] = {}
    for value, evidence_item, confidence in values:
        items = value if isinstance(value, list) else [value]
        for item in items:
            if _value_is_empty(item):
                continue
            item_key = _field_key(item)
            if item_key not in {_field_key(existing) for existing in flattened}:
                flattened.append(item)
            candidate = candidates_by_key.setdefault(
                item_key,
                {"value": item, "evidence": [], "confidences": []},
            )
            if evidence_item is not None and evidence_item not in candidate["evidence"]:
                candidate["evidence"].append(evidence_item)
            if confidence is not None:
                candidate["confidences"].append(confidence)
        if evidence_item is not None and evidence_item not in evidence:
            evidence.append(evidence_item)
        if confidence is not None:
            confidences.append(confidence)

    if not flattened:
        return None

    return WorkerDocumentExtractionFieldResult(
        value=flattened,
        dtype="list",
        required=required,
        evidence=evidence[:MAX_FIELD_EVIDENCE],
        candidate_values=[
            _candidate_payload(
                value=candidate["value"],
                confidence=max(candidate["confidences"])
                if candidate["confidences"]
                else None,
                evidence=candidate["evidence"],
            )
            for candidate in candidates_by_key.values()
        ],
        confidence=max(confidences) if confidences else None,
        conflict=False,
        validation_errors=_field_validation_errors(flattened, dtype="list"),
    )
