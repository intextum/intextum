"""Helpers for using prior research reports as follow-up chat context."""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage

from chat.collector import ChatSourceCollector
from chat.sources import (
    CollectedSource,
    StoredSourcePayload,
    parse_stored_source_payloads,
)

RESEARCH_REPORT_CONTEXT_MAX_CHARS = 12_000
RESEARCH_REPORT_MAX_FOLLOW_UP_SECTIONS = 2
_CITATION_PATTERN = re.compile(r"\[(\d+)\]")
_TOKEN_PATTERN = re.compile(r"[a-z0-9]{3,}")
_REPORT_SCORING_STOPWORDS = {
    "about",
    "after",
    "also",
    "been",
    "did",
    "from",
    "have",
    "into",
    "more",
    "over",
    "say",
    "section",
    "that",
    "than",
    "the",
    "them",
    "they",
    "this",
    "what",
    "when",
    "with",
    "would",
}


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
            continue
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "".join(parts)


def _report_source_context_line(source: CollectedSource) -> str:
    label = source.title or source.display_name or source.file_path
    line = f"[{source.citation_index}] {label}"
    if source.page_numbers:
        joined_pages = ", ".join(str(page) for page in source.page_numbers)
        line += f" (pages {joined_pages})"
    if source.quote:
        line += f' - "{source.quote[:160]}"'
    return line


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).strip()


def _scoring_terms(value: str) -> set[str]:
    normalized = _normalize_text(value).lower()
    return {
        token
        for token in _TOKEN_PATTERN.findall(normalized)
        if token not in _REPORT_SCORING_STOPWORDS
    }


def _used_citation_indices(text: str) -> list[int]:
    seen: set[int] = set()
    ordered: list[int] = []
    for match in _CITATION_PATTERN.finditer(text):
        value = int(match.group(1))
        if value not in seen:
            ordered.append(value)
            seen.add(value)
    return ordered


def _clip_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    if limit <= 3:
        return value[:limit]
    return value[: limit - 3].rstrip() + "..."


def _latest_human_message_text(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if not isinstance(message, HumanMessage):
            continue
        text = _message_text(message.content).strip()
        if text:
            return text
    return ""


def _report_sections(raw_metadata: dict[str, Any]) -> list[dict[str, Any]]:
    raw_sections = raw_metadata.get("sections")
    if not isinstance(raw_sections, list):
        return []

    sections: list[dict[str, Any]] = []
    for index, raw_section in enumerate(raw_sections):
        if not isinstance(raw_section, dict):
            continue
        raw_heading = raw_section.get("heading")
        heading = raw_heading.strip() if isinstance(raw_heading, str) else ""
        if not heading:
            heading = f"Section {index + 1}"

        raw_body = raw_section.get("body")
        body = (
            _message_text(raw_body).strip()
            if not isinstance(raw_body, str)
            else raw_body.strip()
        )
        if not body:
            continue

        sections.append(
            {
                "heading": heading,
                "body": body,
                "citation_indices": _used_citation_indices(body),
            }
        )
    return sections


def _section_relevance_score(
    *,
    follow_up_text: str,
    section: dict[str, Any],
) -> float:
    follow_up_terms = _scoring_terms(follow_up_text)
    if not follow_up_terms:
        return 0.0

    heading = section.get("heading") if isinstance(section.get("heading"), str) else ""
    body = section.get("body") if isinstance(section.get("body"), str) else ""

    heading_terms = _scoring_terms(heading)
    body_terms = _scoring_terms(body)
    score = 0.0
    score += len(follow_up_terms & heading_terms) * 2.5
    score += len(follow_up_terms & body_terms) * 0.9

    normalized_follow_up = _normalize_text(follow_up_text).lower()
    normalized_heading = _normalize_text(heading).lower()
    if normalized_heading and normalized_heading in normalized_follow_up:
        score += 2.0
    if normalized_follow_up and normalized_follow_up in _normalize_text(body).lower():
        score += 1.0

    return score


def _select_relevant_report_sections(
    *,
    report_sections: list[dict[str, Any]],
    follow_up_text: str,
) -> list[dict[str, Any]]:
    if not report_sections:
        return []

    scored_sections: list[tuple[float, int, dict[str, Any]]] = []
    for index, section in enumerate(report_sections):
        score = _section_relevance_score(
            follow_up_text=follow_up_text,
            section=section,
        )
        if score <= 0:
            continue
        scored_sections.append((score, index, section))

    if not scored_sections:
        return []

    top_score = max(score for score, _, _ in scored_sections)
    ranked_sections = sorted(
        scored_sections,
        key=lambda item: (item[0], -item[1]),
        reverse=True,
    )
    return [
        section
        for score, _, section in ranked_sections
        if score >= max(1.5, top_score * 0.55)
    ][:RESEARCH_REPORT_MAX_FOLLOW_UP_SECTIONS]


def _select_section_sources(
    *,
    report_sources: list[StoredSourcePayload],
    report_sections: list[dict[str, Any]],
) -> list[CollectedSource]:
    selected_indices = {
        citation_index
        for section in report_sections
        for citation_index in section.get("citation_indices", [])
        if isinstance(citation_index, int)
    }
    if not selected_indices:
        return []

    selected_sources: list[CollectedSource] = []
    seen_keys: set[tuple[str, int | str | None]] = set()
    for stored_source in report_sources:
        if stored_source.citation_index not in selected_indices:
            continue
        key = stored_source.dedupe_key()
        if key in seen_keys:
            continue
        seen_keys.add(key)
        selected_sources.append(stored_source.to_collected_source())
    return selected_sources


def _selected_section_context(report_sections: list[dict[str, Any]]) -> str:
    remaining = RESEARCH_REPORT_CONTEXT_MAX_CHARS
    parts: list[str] = []

    for section in report_sections:
        heading = (
            section.get("heading")
            if isinstance(section.get("heading"), str)
            else "Section"
        )
        body = section.get("body") if isinstance(section.get("body"), str) else ""
        section_text = f"## {heading}\n\n{body}".strip()
        clipped = _clip_text(section_text, remaining)
        if not clipped:
            break
        parts.append(clipped)
        remaining -= len(clipped) + 2
        if remaining <= 0:
            break

    return "\n\n".join(parts).strip()


def build_latest_research_report_context(
    messages: list[AnyMessage],
    *,
    source_collector: ChatSourceCollector,
) -> str | None:
    follow_up_text = _latest_human_message_text(messages)

    for message in reversed(messages):
        if not isinstance(message, AIMessage):
            continue
        raw_metadata = (getattr(message, "additional_kwargs", {}) or {}).get("metadata")
        if (
            not isinstance(raw_metadata, dict)
            or raw_metadata.get("kind") != "research_report"
        ):
            continue

        report_text = _message_text(message.content).strip()
        if not report_text:
            return None

        stored_report_sources = parse_stored_source_payloads(
            (getattr(message, "additional_kwargs", {}) or {}).get("sources")
        )
        selected_sections = _select_relevant_report_sections(
            report_sections=_report_sections(raw_metadata),
            follow_up_text=follow_up_text,
        )
        if selected_sections:
            selected_report_sources = _select_section_sources(
                report_sources=stored_report_sources,
                report_sections=selected_sections,
            )
            section_signature = (
                ",".join(
                    str(citation_index)
                    for section in selected_sections
                    for citation_index in section.get("citation_indices", [])
                    if isinstance(citation_index, int)
                )
                or "sections"
            )
            context_key_suffix = f"sections:{section_signature}"
            report_context_label = "Relevant report sections"
            report_context_body = _selected_section_context(selected_sections)
        else:
            selected_report_sources = [
                stored_source.to_collected_source()
                for stored_source in stored_report_sources
            ]
            context_key_suffix = "full-report"
            report_context_label = "Report content"
            report_context_body = _clip_text(
                report_text, RESEARCH_REPORT_CONTEXT_MAX_CHARS
            )

        report_id = raw_metadata.get("report_id")
        context_key_prefix = (
            f"research-report:{report_id}"
            if isinstance(report_id, str) and report_id
            else f"research-report-message:{getattr(message, 'id', 'latest')}"
        )
        report_sources = source_collector.prime_context_sources(
            key=f"{context_key_prefix}:{context_key_suffix}",
            sources=selected_report_sources,
        )

        title = raw_metadata.get("title")
        header = (
            "A deep research report already exists in this conversation. "
            "Treat it as authoritative conversation context for follow-up questions "
            "about the report, its findings, or its conclusions."
        )
        if isinstance(title, str) and title.strip():
            header += f"\nReport title: {title.strip()}"
        if selected_sections:
            selected_headings = ", ".join(
                section["heading"]
                for section in selected_sections
                if isinstance(section.get("heading"), str)
            )
            if selected_headings:
                header += (
                    "\nFor this follow-up, prefer the most relevant report sections: "
                    f"{selected_headings}"
                )
        if report_sources:
            cited_sources = "\n".join(
                _report_source_context_line(source)
                for source in report_sources
                if isinstance(source.citation_index, int)
            )
            header += (
                "\nWhen you answer from this report, cite the relevant report source "
                "markers inline using the same [n] notation."
            )
            return (
                f"{header}\n\n"
                f"Report-backed sources:\n{cited_sources}\n\n"
                f"{report_context_label}:\n{report_context_body}"
            )

        return f"{header}\n\n{report_context_label}:\n{report_context_body}"

    return None
