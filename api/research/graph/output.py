"""Output and citation helpers for the research graph."""

from __future__ import annotations

import re
from typing import Any

_CITATION_PATTERN = re.compile(r"\[(\d+)\]")
_MAX_IMAGES = 4


def _used_citation_indices(text: str) -> list[int]:
    seen: set[int] = set()
    ordered: list[int] = []
    for match in _CITATION_PATTERN.finditer(text):
        value = int(match.group(1))
        if value not in seen:
            ordered.append(value)
            seen.add(value)
    return ordered


def _select_images(
    *,
    sections: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    referenced: set[int] = set()
    for section in sections:
        body = section.get("body")
        if isinstance(body, str):
            referenced.update(_used_citation_indices(body))

    selected: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for source in sources:
        citation_index = source.get("citation_index")
        if not isinstance(citation_index, int) or citation_index not in referenced:
            continue
        title = source.get("title") if isinstance(source.get("title"), str) else None
        for image_url in (
            source.get("images", []) if isinstance(source.get("images"), list) else []
        ):
            if (
                not isinstance(image_url, str)
                or not image_url
                or image_url in seen_urls
            ):
                continue
            selected.append(
                {
                    "url": image_url,
                    "title": title,
                    "citation_index": citation_index,
                }
            )
            seen_urls.add(image_url)
            if len(selected) >= _MAX_IMAGES:
                return selected
    return selected


def _verification_issues(
    *,
    sections: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    section_evidence: list[dict[str, Any]] | None = None,
) -> list[str]:
    available_indices = {
        source["citation_index"]
        for source in sources
        if isinstance(source, dict) and isinstance(source.get("citation_index"), int)
    }
    issues: list[str] = []
    used_any = False

    for section_index, section in enumerate(sections):
        heading = (
            section.get("heading")
            if isinstance(section.get("heading"), str)
            else "Section"
        )
        body = section.get("body") if isinstance(section.get("body"), str) else ""
        used_indices = _used_citation_indices(body)
        if used_indices:
            used_any = True
        invalid = [index for index in used_indices if index not in available_indices]
        if invalid:
            issues.append(
                f"{heading}: invalid citations {', '.join(str(item) for item in invalid)}"
            )

        allowed_indices: set[int] = set()
        if isinstance(section_evidence, list) and section_index < len(section_evidence):
            allowed_indices = {
                item
                for item in section_evidence[section_index].get("citation_indices", [])
                if isinstance(item, int)
            }
        if allowed_indices and not used_indices:
            issues.append(
                f"{heading}: section evidence was retrieved but the draft cites none of it"
            )
        cross_section = [
            index
            for index in used_indices
            if index in available_indices
            and allowed_indices
            and index not in allowed_indices
        ]
        if cross_section:
            issues.append(
                f"{heading}: cites sources outside the section evidence {', '.join(str(item) for item in cross_section)}"
            )
        if used_indices and not allowed_indices:
            issues.append(f"{heading}: cites sources without assigned section evidence")

    if sources and not used_any:
        issues.append("The report does not cite any retrieved evidence.")
    return issues


def _compose_markdown(
    *,
    title: str | None,
    sections: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> str:
    safe_title = title or "Research Report"
    parts = [f"# {safe_title}"]
    for section in sections:
        heading = (
            section.get("heading")
            if isinstance(section.get("heading"), str)
            else "Section"
        )
        body = section.get("body") if isinstance(section.get("body"), str) else ""
        parts.append(f"## {heading}\n\n{body}".strip())

    if sources:
        source_lines = []
        for source in sources:
            citation_index = source.get("citation_index")
            prefix = f"[{citation_index}] " if isinstance(citation_index, int) else ""
            title_text = (
                source.get("title") if isinstance(source.get("title"), str) else None
            )
            display_name = (
                source.get("display_name")
                if isinstance(source.get("display_name"), str)
                else None
            )
            file_path = (
                source.get("file_path")
                if isinstance(source.get("file_path"), str)
                else "unknown"
            )
            page_numbers = (
                source.get("page_numbers")
                if isinstance(source.get("page_numbers"), list)
                else []
            )
            page_text = (
                f" (pages {', '.join(str(page) for page in page_numbers if isinstance(page, int))})"
                if page_numbers
                else ""
            )
            label = title_text or display_name or file_path.split("/")[-1]
            source_lines.append(f"- {prefix}{label}: `{file_path}`{page_text}")
        parts.append("## Sources\n\n" + "\n".join(source_lines))

    return "\n\n".join(parts).strip()
