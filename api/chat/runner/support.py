"""Pure support helpers for background chat-run execution."""

from __future__ import annotations

from typing import Any

from chat.submissions import build_human_messages
from chat.time import iso_now
from models.user import User
from models.user import UserEventRecord


def payload_user(payload: Any) -> User:
    """Rebuild the normalized user model embedded in one run payload."""
    return User(**payload.user.model_dump())


def build_chat_user_event(
    *,
    payload: Any,
    kind: str,
    status: str,
) -> UserEventRecord:
    """Build one conversation-scoped user event for chat-run status changes."""
    return UserEventRecord(
        kind=kind,
        resource_type="conversation",
        resource_id=payload.conversation_id,
        status=status,
        metadata={"conversation_id": payload.conversation_id},
        created_at=iso_now(),
    )


def build_research_user_event(
    *,
    payload: Any,
    kind: str,
    status: str,
) -> UserEventRecord:
    """Build one conversation/report-scoped user event for research runs."""
    return UserEventRecord(
        kind=kind,
        resource_type="conversation",
        resource_id=payload.conversation_id,
        status=status,
        metadata={
            "conversation_id": payload.conversation_id,
            "report_id": payload.research_report_id,
        },
        created_at=iso_now(),
    )


def progress_message(node_name: str) -> str:
    """Return the UI-facing progress label for one research node."""
    labels = {
        "plan_research": "Planned research outline.",
        "retrieve_evidence": "Collected supporting evidence.",
        "draft_report": "Drafted the report.",
        "verify_report": "Validated citations and assembled the final report.",
    }
    return labels.get(node_name, node_name)


def research_prompt(payload: Any) -> str:
    """Extract the primary research prompt from the submitted human messages."""
    human_messages = build_human_messages(
        payload.messages,
        context_file_paths=payload.context_file_paths,
    )
    if not human_messages:
        raise ValueError("messages must include at least one user message")
    return str(human_messages[0].content)


def normalize_research_final_state(final_state: dict[str, Any]) -> dict[str, Any]:
    """Normalize the graph final state into the fields persisted on reports."""
    return {
        "title": final_state.get("title")
        if isinstance(final_state.get("title"), str)
        else None,
        "outline": [
            item for item in final_state.get("outline", []) if isinstance(item, str)
        ],
        "sections": [
            item for item in final_state.get("sections", []) if isinstance(item, dict)
        ],
        "sources": [
            item for item in final_state.get("sources", []) if isinstance(item, dict)
        ],
        "images": [
            item for item in final_state.get("images", []) if isinstance(item, dict)
        ],
        "verification_issues": [
            item
            for item in final_state.get("verification_issues", [])
            if isinstance(item, str)
        ],
        "content_markdown": (
            final_state.get("content_markdown")
            if isinstance(final_state.get("content_markdown"), str)
            else ""
        ),
    }
