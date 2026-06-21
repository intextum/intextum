"""Structured fact and scoring helpers for the research graph."""

from __future__ import annotations

import json
import re
from typing import Any

_TOKEN_PATTERN = re.compile(r"[a-z0-9]{3,}")
_MAX_STRUCTURED_FACT_FILES = 6
_MAX_STRUCTURED_FACT_FIELDS = 10
_MAX_STRUCTURED_FACT_EVIDENCE = 4
_MAX_STRUCTURED_FACT_VALUE_CHARS = 180
_MAX_STRUCTURED_FACT_PROMPT_CHARS = 4_000
_SCORING_STOPWORDS = {
    "and",
    "are",
    "but",
    "for",
    "from",
    "has",
    "have",
    "how",
    "not",
    "that",
    "the",
    "their",
    "them",
    "this",
    "what",
    "when",
    "which",
    "with",
}


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).strip()


def _clip_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    if limit <= 3:
        return value[:limit]
    return value[: limit - 3].rstrip() + "..."


def _scoring_terms(value: str) -> set[str]:
    normalized = _normalize_text(value).lower()
    return {
        token
        for token in _TOKEN_PATTERN.findall(normalized)
        if token not in _SCORING_STOPWORDS
    }


def _stringify_structured_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return _clip_text(value.strip(), _MAX_STRUCTURED_FACT_VALUE_CHARS)

    try:
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=False)
    except TypeError:
        rendered = str(value)
    return _clip_text(rendered, _MAX_STRUCTURED_FACT_VALUE_CHARS)


def _structured_fact_terms(item: dict[str, Any]) -> set[str]:
    parts: list[str] = []
    api_path = item.get("api_path")
    if isinstance(api_path, str):
        parts.append(api_path)
    document_class = item.get("document_class")
    if isinstance(document_class, str):
        parts.append(document_class)
    extraction_data = item.get("extraction_data")
    if isinstance(extraction_data, dict):
        for field_name, field_value in extraction_data.items():
            parts.append(str(field_name))
            parts.append(_stringify_structured_value(field_value))
    return _scoring_terms("\n".join(parts))


def _structured_fact_source_label(value: Any) -> str | None:
    if value == "user_override":
        return "user correction"
    if value == "document_processing":
        return "document processing"
    return None


def _structured_fact_review_label(value: Any) -> str | None:
    if value == "accepted":
        return "human-reviewed accepted"
    if value == "corrected":
        return "human-reviewed corrected"
    return None


def _structured_fact_metadata_suffix(*values: str | None) -> str:
    labels = [value for value in values if isinstance(value, str) and value]
    if not labels:
        return ""
    return f" ({', '.join(labels)})"


def _structured_fact_review_bonus(item: dict[str, Any]) -> float:
    best_bonus = 0.0
    for key in ("document_class_review_status", "extraction_review_status"):
        value = item.get(key)
        if value == "accepted":
            best_bonus = max(best_bonus, 0.55)
        elif value == "corrected":
            best_bonus = max(best_bonus, 0.7)
    reviewed_evidence = item.get("reviewed_evidence")
    if isinstance(reviewed_evidence, list) and reviewed_evidence:
        best_bonus += 0.15
    return best_bonus


def _structured_fact_evidence_suffix(item: dict[str, Any]) -> str:
    details: list[str] = []
    page_numbers = item.get("page_numbers")
    if isinstance(page_numbers, list) and page_numbers:
        details.append(
            f"pages {', '.join(str(page) for page in page_numbers if isinstance(page, int))}"
        )
    doc_refs = item.get("doc_refs")
    if isinstance(doc_refs, list) and doc_refs:
        details.append(
            "refs " + ", ".join(ref for ref in doc_refs if isinstance(ref, str) and ref)
        )
    if not details:
        return ""
    return f" ({'; '.join(details)})"


def _relevant_structured_facts(
    *,
    structured_facts: list[dict[str, Any]],
    prompt: str,
    heading: str | None = None,
    question: str | None = None,
) -> list[dict[str, Any]]:
    if not structured_facts:
        return []

    prompt_terms = _scoring_terms(prompt)
    heading_terms = _scoring_terms(heading or "")
    question_terms = _scoring_terms(question or "")
    scored: list[tuple[float, int, dict[str, Any]]] = []
    for index, item in enumerate(structured_facts):
        item_terms = _structured_fact_terms(item)
        score = 0.0
        score += len(prompt_terms & item_terms) * 0.45
        score += len(heading_terms & item_terms) * 1.3
        score += len(question_terms & item_terms) * 1.1
        score += _structured_fact_review_bonus(item)
        if score <= 0:
            continue
        scored.append((score, index, item))

    if not scored:
        return structured_facts[: min(2, len(structured_facts))]

    top_score = max(score for score, _, _ in scored)
    ranked = sorted(scored, key=lambda item: (item[0], -item[1]), reverse=True)
    return [item for score, _, item in ranked if score >= max(0.35, top_score * 0.55)][
        : min(_MAX_STRUCTURED_FACT_FILES, 3)
    ]


def _structured_facts_block(
    *,
    structured_facts: list[dict[str, Any]],
    prompt: str,
    heading: str | None = None,
    question: str | None = None,
) -> str:
    selected = _relevant_structured_facts(
        structured_facts=structured_facts[:_MAX_STRUCTURED_FACT_FILES],
        prompt=prompt,
        heading=heading,
        question=question,
    )
    if not selected:
        return ""

    sections: list[str] = []
    for item in selected:
        api_path = item.get("api_path")
        if not isinstance(api_path, str) or not api_path:
            continue
        lines = [f"File: {api_path}"]
        document_class = item.get("document_class")
        if isinstance(document_class, str) and document_class.strip():
            source_label = _structured_fact_source_label(
                item.get("document_class_source")
            )
            review_label = _structured_fact_review_label(
                item.get("document_class_review_status")
            )
            suffix = _structured_fact_metadata_suffix(source_label, review_label)
            lines.append(f"- Document class: {document_class.strip()}{suffix}")

        extraction_data = item.get("extraction_data")
        if isinstance(extraction_data, dict) and extraction_data:
            source_label = _structured_fact_source_label(item.get("extraction_source"))
            review_label = _structured_fact_review_label(
                item.get("extraction_review_status")
            )
            suffix = _structured_fact_metadata_suffix(source_label, review_label)
            lines.append(f"- Extracted fields{suffix}:")
            entries = list(extraction_data.items())
            for field_name, field_value in entries[:_MAX_STRUCTURED_FACT_FIELDS]:
                lines.append(
                    f"  - {field_name}: {_stringify_structured_value(field_value)}"
                )
            remaining = len(entries) - _MAX_STRUCTURED_FACT_FIELDS
            if remaining > 0:
                lines.append(f"  - ... {remaining} more fields")

        reviewed_evidence = item.get("reviewed_evidence")
        if isinstance(reviewed_evidence, list) and reviewed_evidence:
            lines.append("- Reviewed enrichment evidence snippets:")
            for evidence_item in reviewed_evidence[:_MAX_STRUCTURED_FACT_EVIDENCE]:
                if not isinstance(evidence_item, dict):
                    continue
                label = evidence_item.get("label")
                snippet = evidence_item.get("snippet")
                if (
                    not isinstance(label, str)
                    or not label
                    or not isinstance(snippet, str)
                    or not snippet
                ):
                    continue
                lines.append(
                    f"  - {label}{_structured_fact_evidence_suffix(evidence_item)}: "
                    f"{_clip_text(snippet, _MAX_STRUCTURED_FACT_VALUE_CHARS)}"
                )
            remaining = len(reviewed_evidence) - _MAX_STRUCTURED_FACT_EVIDENCE
            if remaining > 0:
                lines.append(
                    f"  - ... {remaining} more reviewed enrichment evidence snippets"
                )

        sections.append("\n".join(lines))

    return _clip_text("\n\n".join(sections), _MAX_STRUCTURED_FACT_PROMPT_CHARS)
