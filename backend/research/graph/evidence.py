"""Evidence ranking helpers for the research graph."""

from __future__ import annotations

from typing import Any

from research.graph.structured import (
    _MAX_STRUCTURED_FACT_FILES,
    _normalize_text,
    _relevant_structured_facts,
    _scoring_terms,
    _structured_fact_review_bonus,
)

_MAX_SECTION_SOURCES = 4
_MAX_SECTION_SOURCES_PER_FILE = 2
_MAX_SECTION_REVIEWED_EVIDENCE = 2
_VECTOR_SCORE_WEIGHT = 2.0


def _section_candidate_score(
    *,
    chunk: Any,
    file_path: str,
    heading_text: str,
    question_text: str,
    prompt_terms: set[str],
    heading_terms: set[str],
    question_terms: set[str],
    query_terms: set[str],
    query_index: int,
    rank_index: int,
) -> float:
    haystack = "\n".join(
        [
            file_path,
            chunk.text if isinstance(chunk.text, str) else "",
            " ".join(item for item in chunk.doc_refs if isinstance(item, str)),
        ]
    )
    chunk_terms = _scoring_terms(haystack)
    score = 0.0
    score += len(prompt_terms & chunk_terms) * 0.5
    score += len(heading_terms & chunk_terms) * 1.8
    score += len(question_terms & chunk_terms) * 1.4
    score += len(query_terms & chunk_terms) * 0.8
    score += max(0, 4 - min(rank_index, 4)) * 0.15
    score -= query_index * 0.05
    raw_vector_score = getattr(chunk, "score", None)
    if isinstance(raw_vector_score, (int, float)):
        score += max(0.0, min(float(raw_vector_score), 1.0)) * _VECTOR_SCORE_WEIGHT

    normalized_haystack = _normalize_text(haystack).lower()
    heading_phrase = _normalize_text(heading_text).lower()
    question_phrase = _normalize_text(question_text).lower()
    if heading_phrase and heading_phrase in normalized_haystack:
        score += 1.2
    if question_phrase and question_phrase in normalized_haystack:
        score += 0.8
    return score


def _rank_section_candidates(
    *,
    candidates: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    ranked_candidates = sorted(
        candidates.values(),
        key=lambda item: (
            item["score"] + (len(item["query_indices"]) * 0.9),
            len(item["query_indices"]),
            -item["first_query_index"],
            -item["first_rank_index"],
        ),
        reverse=True,
    )

    selected: list[dict[str, Any]] = []
    file_counts: dict[str, int] = {}
    for item in ranked_candidates:
        file_path = item["file_path"]
        if file_counts.get(file_path, 0) >= _MAX_SECTION_SOURCES_PER_FILE:
            continue
        selected.append(item)
        file_counts[file_path] = file_counts.get(file_path, 0) + 1
        if len(selected) >= _MAX_SECTION_SOURCES:
            return selected

    return selected


def _reviewed_section_candidate_score(
    *,
    api_path: str,
    label: str,
    snippet: str,
    prompt_terms: set[str],
    heading_terms: set[str],
    question_terms: set[str],
    review_bonus: float,
) -> float:
    haystack = "\n".join((api_path, label, snippet))
    snippet_terms = _scoring_terms(haystack)
    score = 0.0
    score += len(prompt_terms & snippet_terms) * 0.45
    score += len(heading_terms & snippet_terms) * 1.25
    score += len(question_terms & snippet_terms) * 1.1
    score += review_bonus
    return score


def _reviewed_evidence_section_candidates(
    *,
    structured_facts: list[dict[str, Any]],
    prompt: str,
    heading: str,
    question: str,
    prompt_terms: set[str],
    heading_terms: set[str],
    question_terms: set[str],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    selected_facts = _relevant_structured_facts(
        structured_facts=structured_facts,
        prompt=prompt,
        heading=heading,
        question=question,
    )
    for fact in selected_facts[:_MAX_STRUCTURED_FACT_FILES]:
        api_path = fact.get("api_path")
        if not isinstance(api_path, str) or not api_path:
            continue
        review_bonus = _structured_fact_review_bonus(fact)
        reviewed_evidence = fact.get("reviewed_evidence")
        if not isinstance(reviewed_evidence, list):
            continue
        for evidence_item in reviewed_evidence[:_MAX_SECTION_REVIEWED_EVIDENCE]:
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
            score = _reviewed_section_candidate_score(
                api_path=api_path,
                label=label,
                snippet=snippet,
                prompt_terms=prompt_terms,
                heading_terms=heading_terms,
                question_terms=question_terms,
                review_bonus=review_bonus,
            )
            if score <= 0:
                continue
            candidates.append(
                {
                    "file_path": api_path,
                    "title": f"Reviewed enrichment evidence: {label}",
                    "kind": "reviewed_enrichment",
                    "text": snippet,
                    "page_numbers": [
                        page
                        for page in evidence_item.get("page_numbers", [])
                        if isinstance(page, int)
                    ],
                    "doc_refs": [
                        ref
                        for ref in evidence_item.get("doc_refs", [])
                        if isinstance(ref, str) and ref
                    ],
                    "images": [],
                    "score": score,
                    "first_query_index": 0,
                    "first_rank_index": 0,
                    "query_indices": {0},
                }
            )
    return candidates
