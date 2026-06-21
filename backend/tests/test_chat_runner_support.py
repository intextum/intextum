"""Focused tests for chat runner support helpers."""

from types import SimpleNamespace

import pytest

from chat.runner.support import (
    build_chat_user_event,
    build_research_user_event,
    normalize_research_final_state,
    progress_message,
    research_prompt,
)
from models.chat.runs import ChatRunRequestPayload


def _payload() -> ChatRunRequestPayload:
    return ChatRunRequestPayload.model_validate(
        {
            "conversation_id": "thread-1",
            "user": {"username": "testuser", "sub": "sub-testuser"},
            "messages": [
                {
                    "id": "msg-1",
                    "type": "human",
                    "content": "Create a grounded retention report.",
                }
            ],
            "context_file_paths": ["docs/report.pdf"],
        }
    )


def test_build_chat_user_event_uses_conversation_metadata():
    event = build_chat_user_event(
        payload=_payload(),
        kind="chat.run.completed",
        status="COMPLETED",
    )

    assert event.kind == "chat.run.completed"
    assert event.status == "COMPLETED"
    assert event.resource_id == "thread-1"
    assert event.metadata == {"conversation_id": "thread-1"}


def test_build_research_user_event_includes_report_id():
    payload = _payload().model_copy(update={"research_report_id": "report_123"})
    event = build_research_user_event(
        payload=payload,
        kind="research.run.completed",
        status="COMPLETED",
    )

    assert event.kind == "research.run.completed"
    assert event.metadata == {
        "conversation_id": "thread-1",
        "report_id": "report_123",
    }


def test_progress_message_returns_label_or_node_name():
    assert progress_message("plan_research") == "Planned research outline."
    assert progress_message("custom_phase") == "custom_phase"


def test_research_prompt_returns_first_human_message():
    assert research_prompt(_payload()) == "Create a grounded retention report."


def test_research_prompt_requires_human_message():
    payload = SimpleNamespace(messages=[], context_file_paths=[])

    with pytest.raises(
        ValueError, match="messages must include at least one user message"
    ):
        research_prompt(payload)


def test_normalize_research_final_state_filters_invalid_items():
    normalized = normalize_research_final_state(
        {
            "title": "Retention Report",
            "outline": ["Findings", 4],
            "sections": [{"heading": "Findings", "body": "Grounded."}, "skip"],
            "sources": [{"file_path": "docs/report.pdf"}, "skip"],
            "images": [{"url": "https://example.com/chart.png"}, None],
            "verification_issues": ["Needs citation check", 1],
            "content_markdown": "# Report",
        }
    )

    assert normalized == {
        "title": "Retention Report",
        "outline": ["Findings"],
        "sections": [{"heading": "Findings", "body": "Grounded."}],
        "sources": [{"file_path": "docs/report.pdf"}],
        "images": [{"url": "https://example.com/chart.png"}],
        "verification_issues": ["Needs citation check"],
        "content_markdown": "# Report",
    }
