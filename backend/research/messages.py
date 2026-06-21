"""Helpers for persisting deep research output into conversation threads."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage


def build_research_report_message(
    *,
    report_id: str,
    content_markdown: str,
    sources: list[dict[str, Any]],
    metadata: dict[str, Any],
    created_at: str,
) -> AIMessage:
    """Build the assistant message persisted for one completed research report."""
    additional_kwargs: dict[str, Any] = {
        "created_at": created_at,
        "metadata": metadata,
    }
    if sources:
        additional_kwargs["sources"] = sources

    return AIMessage(
        id=f"research-report:{report_id}",
        content=content_markdown,
        additional_kwargs=additional_kwargs,
    )
