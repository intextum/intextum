"""Prompt and section-planning helpers for the research graph."""

from __future__ import annotations

from typing import Any

from research.graph.structured import _normalize_text, _structured_facts_block

_MAX_SECTION_QUERIES = 3


def _fallback_title(prompt: str) -> str:
    stripped = " ".join(prompt.split())
    if len(stripped) <= 80:
        return stripped
    return stripped[:77].rstrip() + "..."


def _planner_prompt(state) -> str:
    scope = ", ".join(state.get("context_file_paths", [])) or "all accessible documents"
    structured_facts = _structured_facts_block(
        structured_facts=[
            item for item in state.get("structured_facts", []) if isinstance(item, dict)
        ],
        prompt=state["prompt"],
    )
    prompt = (
        "Create a focused research plan for the following task.\n\n"
        f"Prompt:\n{state['prompt']}\n\n"
        f"Scope:\n{scope}\n\n"
        "Return JSON with this shape:\n"
        "{"
        '"title": string,'
        '"questions": string[],'
        '"outline": string[]'
        "}\n\n"
        "Rules:\n"
        "- Keep 3 to 6 questions.\n"
        "- Keep 3 to 6 outline sections.\n"
        "- Make the title concise and useful.\n"
        "- Focus on document-grounded analysis."
    )
    if structured_facts:
        prompt += (
            "\n\nStructured document facts:\n"
            f"{structured_facts}\n\n"
            "Use these file-level facts to improve planning and identify concrete entities, dates, amounts, and identifiers. "
            "Prefer human-reviewed accepted or corrected facts, especially when reviewed enrichment evidence snippets are present. "
            "Treat unreviewed document-processing output as tentative orientation, not as standalone citations."
        )
    return prompt


def _evidence_block(evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return "No supporting evidence was retrieved from the available documents."

    parts: list[str] = []
    for item in evidence:
        page_text = ""
        if item["page_numbers"]:
            page_text = (
                f" (pages {', '.join(str(page) for page in item['page_numbers'])})"
            )
        refs_text = ""
        if item["doc_refs"]:
            refs_text = f"\nRefs: {', '.join(item['doc_refs'])}"
        parts.append(
            f"[{item['citation_index']}] {item['file_path']}{page_text}\n"
            f"{item['text']}{refs_text}"
        )
    return "\n\n---\n\n".join(parts)


def _section_plans(state) -> list[dict[str, str]]:
    outline = [
        heading.strip()
        for heading in (state.get("outline") or [])
        if isinstance(heading, str) and heading.strip()
    ]
    questions = [
        question.strip()
        for question in (state.get("questions") or [])
        if isinstance(question, str) and question.strip()
    ]
    if not outline:
        outline = ["Executive Summary", "Findings", "Recommendations"]

    default_question = (
        _normalize_text(state["prompt"]) or "Summarize the available evidence."
    )
    section_plans: list[dict[str, str]] = []
    for index, heading in enumerate(outline):
        if index < len(questions):
            question = questions[index]
        elif questions:
            question = questions[-1]
        else:
            question = default_question
        section_plans.append({"heading": heading, "question": question})
    return section_plans


def _section_query_candidates(
    *,
    prompt: str,
    heading: str,
    question: str,
) -> list[str]:
    candidates = [
        f"{prompt}\nSection focus: {heading}",
        f"{heading}: {question}",
        question,
        heading,
    ]
    ordered: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = _normalize_text(candidate)
        if not normalized or normalized in seen:
            continue
        ordered.append(normalized)
        seen.add(normalized)
        if len(ordered) >= _MAX_SECTION_QUERIES:
            break
    return ordered


def _section_prompt(state, section_plan: dict[str, Any]) -> str:
    heading = (
        section_plan.get("heading")
        if isinstance(section_plan.get("heading"), str)
        else "Section"
    )
    question = (
        section_plan.get("question")
        if isinstance(section_plan.get("question"), str)
        else _normalize_text(state["prompt"])
    )
    evidence = [
        item for item in section_plan.get("evidence", []) if isinstance(item, dict)
    ]
    structured_facts = _structured_facts_block(
        structured_facts=[
            item for item in state.get("structured_facts", []) if isinstance(item, dict)
        ],
        prompt=state["prompt"],
        heading=heading,
        question=question,
    )
    structured_facts_prompt = (
        "Structured file facts:\n"
        f"{structured_facts}\n\n"
        "Prefer human-reviewed accepted or corrected facts, especially when reviewed enrichment evidence snippets are present, when they help orient the section. "
        "Treat unreviewed document-processing output as tentative file-level orientation only. "
        "The section evidence below remains the authoritative basis for claims and citations.\n\n"
        if structured_facts
        else ""
    )
    return (
        "Write one section of a document-grounded research report using only the section evidence below.\n\n"
        f"Prompt:\n{state['prompt']}\n\n"
        f"Title:\n{state.get('title') or _fallback_title(state['prompt'])}\n\n"
        f"Section heading:\n{heading}\n\n"
        f"Section question:\n{question}\n\n"
        + structured_facts_prompt
        + "Section evidence:\n"
        + _evidence_block(evidence)
        + "\n\nReturn JSON with this shape:\n"
        + '{"body": string}\n\n'
        + "Rules:\n"
        + "- Write only the body for this section.\n"
        + "- Use inline citations like [1] and [3] for factual claims.\n"
        + "- Only cite sources that appear in the section evidence.\n"
        + "- Do not invent citations.\n"
        + "- Do not cite the structured file facts directly; cite only section evidence.\n"
        + "- If evidence is missing, say so explicitly.\n"
        + "- Write clear markdown-compatible prose in the body field."
    )
