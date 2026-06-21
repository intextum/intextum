"""Heading-window heuristics for repeated extraction fields."""

from __future__ import annotations

import re
from typing import Any

from intextum_worker.models import (
    WorkerDocumentExtractionField,
    WorkerDocumentExtractionSchema,
)

_NUMBERED_LIST_START_RE = re.compile(r"^\s*(?:\d+[\.)]|[a-z]\)|[-*•])\s+")

# Fallback section-boundary terms used when a schema does not declare its own.
# Kept German for back-compat with older regulatory-notice schemas.
DEFAULT_SECTION_BOUNDARY_TERMS: tuple[str, ...] = (
    "begründung",
    "rechtsbehelfsbelehrung",
    "gebühr",
    "kosten",
    "hinweis",
    "anhang",
    "anlage",
)

# Language-specific phrases that raise/lower the heading-match score. These
# stay project-local; they only adjust scoring on top of an alias match, so a
# non-German schema still works (the alias match is the load-bearing signal).
_HEADING_PHRASE_BOOSTS: tuple[tuple[str, int], ...] = (
    ("folgenden {alias}", 8),
    ("unter beachtung der {alias}", -4),
)
_HEADING_NEGATIVE_PHRASES: tuple[tuple[str, int], ...] = (("nicht teil", -5),)


def _heading_aliases_for_field(field: WorkerDocumentExtractionField) -> list[str]:
    """Return normalized aliases the field can match against in chunk text."""
    candidates: list[str] = [field.name]
    candidates.extend(getattr(field, "heading_aliases", []) or [])
    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        normalized_candidate = " ".join(candidate.casefold().replace("_", " ").split())
        if not normalized_candidate or normalized_candidate in seen:
            continue
        seen.add(normalized_candidate)
        normalized.append(normalized_candidate)
    return normalized


def _repeated_field_heading_score(
    *,
    normalized_text: str,
    aliases: list[str],
) -> int:
    """Score how likely a chunk is the heading for a repeated field section."""
    score = 0
    for alias in aliases:
        if f"{alias}:" in normalized_text:
            score += 5
        if normalized_text.endswith(f"{alias}:"):
            score += 4
        for phrase_template, delta in _HEADING_PHRASE_BOOSTS:
            if phrase_template.format(alias=alias) in normalized_text:
                score += delta
    for phrase, delta in _HEADING_NEGATIVE_PHRASES:
        if phrase in normalized_text:
            score += delta
    return score


def _looks_like_list_continuation(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return bool(_NUMBERED_LIST_START_RE.match(stripped))


def _section_boundary_terms_for_schema(
    schema: WorkerDocumentExtractionSchema,
) -> tuple[str, ...]:
    declared = getattr(schema, "section_boundary_terms", None) or []
    cleaned = tuple(
        term.casefold().strip()
        for term in declared
        if isinstance(term, str) and term.strip()
    )
    return cleaned or DEFAULT_SECTION_BOUNDARY_TERMS


def _looks_like_section_boundary(text: str, *, boundary_terms: tuple[str, ...]) -> bool:
    if not boundary_terms:
        return False
    stripped = text.strip().casefold()
    if not stripped:
        return False
    for term in boundary_terms:
        if stripped == term:
            return True
        if stripped.startswith(term):
            following = stripped[len(term) : len(term) + 1]
            if not following or not following.isalnum():
                return True
    return False


def _focused_repeated_field_chunks(
    *,
    chunks: list[Any],
    field: WorkerDocumentExtractionField,
    boundary_terms: tuple[str, ...],
) -> list[Any]:
    """Return a small local evidence window for one list/object-list field."""
    aliases = _heading_aliases_for_field(field)
    if not aliases:
        return []

    best_match: tuple[int, int] | None = None
    for index, chunk in enumerate(chunks):
        text = getattr(chunk, "text", "") or ""
        normalized_text = " ".join(text.casefold().split())
        if not any(alias in normalized_text for alias in aliases):
            continue
        score = 1
        score += _repeated_field_heading_score(
            normalized_text=normalized_text,
            aliases=aliases,
        )
        if len(text) <= 400:
            score += 1
        if text.strip().endswith(":"):
            score += 2
        if best_match is None or score > best_match[0]:
            best_match = (score, index)

    if best_match is None:
        return []

    selected_indices = {best_match[1]}
    for index in range(best_match[1] + 1, min(len(chunks), best_match[1] + 4)):
        text = getattr(chunks[index], "text", "") or ""
        if index > best_match[1] + 1 and _looks_like_section_boundary(
            text, boundary_terms=boundary_terms
        ):
            break
        if index == best_match[1] + 1 or _looks_like_list_continuation(text):
            selected_indices.add(index)
            continue
        break
    return [chunks[index] for index in sorted(selected_indices)]
