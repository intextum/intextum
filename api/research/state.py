"""LangGraph state definitions for the deep research workflow."""

from typing import TypedDict


class ResearchGraphState(TypedDict, total=False):
    """State carried through the research graph."""

    prompt: str
    context_file_paths: list[str]
    title: str | None
    questions: list[str]
    outline: list[str]
    single_document_context: dict
    structured_facts: list[dict]
    evidence: list[dict]
    section_evidence: list[dict]
    sources: list[dict]
    sections: list[dict]
    images: list[dict]
    verification_issues: list[str]
    content_markdown: str
