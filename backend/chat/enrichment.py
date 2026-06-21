"""Prompt-time content enrichment context for chat runs."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from chat.collector import ChatSourceCollector
from chat.context import ChatContextScope
from chat.sources import CollectedSource
from models.content.items import ContentItemKind
from models.user import User
from services.content.enrichment_context import load_effective_context_file_enrichment

CONTEXT_ENRICHMENT_MAX_FILES = 8
CONTEXT_ENRICHMENT_MAX_FIELDS = 12
CONTEXT_ENRICHMENT_MAX_REVIEWED_EVIDENCE = 4
CONTEXT_ENRICHMENT_MAX_VALUE_CHARS = 240
CONTEXT_ENRICHMENT_MAX_CHARS = 6_000


def _display_source_label(value: str | None) -> str | None:
    if value == "user_override":
        return "user correction"
    if value == "document_processing":
        return "document processing"
    return None


def _display_review_status_label(value: str | None) -> str | None:
    if value == "accepted":
        return "human-reviewed accepted"
    if value == "corrected":
        return "human-reviewed corrected"
    if value == "dismissed":
        return "human-reviewed dismissed"
    return None


def _metadata_suffix(*values: str | None) -> str:
    labels = [value for value in values if isinstance(value, str) and value]
    if not labels:
        return ""
    return f" ({', '.join(labels)})"


def _clip_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    if limit <= 3:
        return value[:limit]
    return value[: limit - 3].rstrip() + "..."


def _stringify_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return _clip_text(value.strip(), CONTEXT_ENRICHMENT_MAX_VALUE_CHARS)

    try:
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=False)
    except TypeError:
        rendered = str(value)
    return _clip_text(rendered, CONTEXT_ENRICHMENT_MAX_VALUE_CHARS)


def _evidence_suffix(item: dict[str, Any]) -> str:
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


def _reviewed_evidence_source(
    *,
    api_path: str,
    evidence_item: dict[str, Any],
) -> CollectedSource | None:
    label = evidence_item.get("label")
    snippet = evidence_item.get("snippet")
    if (
        not isinstance(label, str)
        or not label
        or not isinstance(snippet, str)
        or not snippet
    ):
        return None
    return CollectedSource(
        file_path=api_path,
        display_name=f"Reviewed enrichment evidence: {label}",
        content_kind=ContentItemKind.FILE,
        source_kind="reviewed_enrichment",
        page_numbers=[
            page
            for page in evidence_item.get("page_numbers", [])
            if isinstance(page, int)
        ],
        doc_refs=[
            ref
            for ref in evidence_item.get("doc_refs", [])
            if isinstance(ref, str) and ref
        ],
        quote=snippet,
        title=f"Reviewed enrichment evidence: {label}",
    )


def _string_value(item: dict[str, Any], key: str) -> str | None:
    value = item.get(key)
    return value if isinstance(value, str) else None


def _append_classification_line(
    lines: list[str],
    *,
    item: dict[str, Any],
    classification_label: str,
) -> None:
    source_label = _display_source_label(_string_value(item, "document_class_source"))
    review_label = _display_review_status_label(
        _string_value(item, "document_class_review_status")
    )
    suffix = _metadata_suffix(source_label, review_label)
    lines.append(f"- Document class: {classification_label}{suffix}")


def _append_extraction_lines(
    lines: list[str],
    *,
    item: dict[str, Any],
    extraction_data: dict[str, Any],
) -> None:
    if not extraction_data:
        return

    extraction_source = _display_source_label(_string_value(item, "extraction_source"))
    review_label = _display_review_status_label(
        _string_value(item, "extraction_review_status")
    )
    source_suffix = _metadata_suffix(extraction_source, review_label)
    lines.append(f"- Extracted fields{source_suffix}:")

    items = list(extraction_data.items())
    for field_name, field_value in items[:CONTEXT_ENRICHMENT_MAX_FIELDS]:
        lines.append(f"  - {field_name}: {_stringify_value(field_value)}")

    remaining = len(items) - CONTEXT_ENRICHMENT_MAX_FIELDS
    if remaining > 0:
        lines.append(f"  - ... {remaining} more fields")


def _reviewed_evidence_sources(
    *,
    api_path: str,
    reviewed_evidence: list[Any],
    source_collector: ChatSourceCollector | None,
) -> list[CollectedSource]:
    if source_collector is None:
        return []
    return source_collector.prime_context_sources(
        key=f"reviewed-enrichment:{api_path}",
        sources=[
            source
            for evidence_item in reviewed_evidence
            for source in [
                _reviewed_evidence_source(
                    api_path=api_path,
                    evidence_item=evidence_item,
                )
            ]
            if source is not None
        ],
    )


def _append_reviewed_evidence_lines(
    lines: list[str],
    *,
    api_path: str,
    reviewed_evidence: list[Any],
    source_collector: ChatSourceCollector | None,
) -> None:
    if not reviewed_evidence:
        return

    assigned_sources = _reviewed_evidence_sources(
        api_path=api_path,
        reviewed_evidence=reviewed_evidence,
        source_collector=source_collector,
    )
    indexed_by_quote = {
        source.quote: source
        for source in assigned_sources
        if isinstance(source.quote, str) and source.quote
    }
    lines.append("- Reviewed enrichment evidence sources:")
    for evidence_item in reviewed_evidence[:CONTEXT_ENRICHMENT_MAX_REVIEWED_EVIDENCE]:
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
        assigned_source = indexed_by_quote.get(snippet)
        prefix = (
            f"  - [{assigned_source.citation_index}] "
            if assigned_source is not None
            and isinstance(assigned_source.citation_index, int)
            else "  - "
        )
        lines.append(
            f"{prefix}{label}{_evidence_suffix(evidence_item)}: "
            f"{_clip_text(snippet, CONTEXT_ENRICHMENT_MAX_VALUE_CHARS)}"
        )

    remaining = len(reviewed_evidence) - CONTEXT_ENRICHMENT_MAX_REVIEWED_EVIDENCE
    if remaining > 0:
        lines.append(f"  - ... {remaining} more reviewed enrichment evidence snippets")


def _format_file_enrichment_block(
    *,
    item: dict[str, Any],
    source_collector: ChatSourceCollector | None = None,
) -> str | None:
    api_path = item.get("api_path")
    classification_label = item.get("document_class")
    extraction_data = item.get("extraction_data")
    if not isinstance(api_path, str) or not api_path:
        return None
    if not isinstance(classification_label, str):
        classification_label = None
    if not classification_label and not isinstance(extraction_data, dict):
        return None

    lines = [f"File: {api_path}"]
    if classification_label:
        _append_classification_line(
            lines,
            item=item,
            classification_label=classification_label,
        )

    if isinstance(extraction_data, dict):
        _append_extraction_lines(lines, item=item, extraction_data=extraction_data)

    reviewed_evidence = item.get("reviewed_evidence")
    if isinstance(reviewed_evidence, list) and reviewed_evidence:
        _append_reviewed_evidence_lines(
            lines,
            api_path=api_path,
            reviewed_evidence=reviewed_evidence,
            source_collector=source_collector,
        )

    return "\n".join(lines)


async def build_context_file_enrichment_context(
    *,
    db: AsyncSession,
    user: User,
    context_scope: ChatContextScope,
    source_collector: ChatSourceCollector | None = None,
) -> str | None:
    """Build a prompt-side summary of effective enrichment for selected files."""
    items = await load_effective_context_file_enrichment(
        db=db,
        user=user,
        context_scope=context_scope,
    )
    if not items:
        return None

    sections: list[str] = []
    for item in items[:CONTEXT_ENRICHMENT_MAX_FILES]:
        section = _format_file_enrichment_block(
            item=item,
            source_collector=source_collector,
        )
        if section is None:
            continue
        sections.append(section)

    if not sections:
        return None

    body = "\n\n".join(sections)
    header = (
        "Some selected context files already have structured document-processing "
        "results. Human-reviewed accepted or corrected enrichment is stronger "
        "file-specific context, and reviewed enrichment evidence snippets are grounded support "
        "for those facts. Unreviewed document-processing output is only "
        "tentative orientation for straightforward facts. When the user asks for "
        "detailed explanation, nuance, or verification, prefer the underlying "
        "document content and cite retrieved document, report, or reviewed enrichment "
        "evidence source markers inline when relevant."
    )
    return _clip_text(f"{header}\n\n{body}", CONTEXT_ENRICHMENT_MAX_CHARS)
