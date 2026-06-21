"""Tests for shaping submitted chat messages into LangChain messages."""

from chat.submissions import (
    build_human_messages,
    build_transcript_messages,
    derive_title_from_text,
)
from models.chat import ChatStreamMessage


def test_derive_title_from_text_trims_and_limits_length():
    """Derived titles should ignore outer whitespace and cap the stored length."""
    long_text = "  " + ("x" * 120) + "  "
    assert derive_title_from_text(long_text) == "x" * 100
    assert derive_title_from_text("   ") is None


def test_build_human_messages_filters_and_normalizes_context_paths(monkeypatch):
    """Only user messages should be kept and annotated with normalized context."""
    monkeypatch.setattr("chat.submissions.iso_now", lambda: "2026-04-21T18:00:00+00:00")

    messages = [
        ChatStreamMessage(id="assistant-1", type="ai", content="Skip me"),
        ChatStreamMessage(
            id="user-1",
            type="human",
            content="Hello world",
            additional_kwargs={"created_at": "2026-04-21T17:00:00+00:00"},
        ),
        ChatStreamMessage(id="user-2", role="user", content="Second message"),
        ChatStreamMessage(id="user-3", type="human", content=["not", "a", "string"]),
    ]

    human_messages = build_human_messages(
        messages,
        context_file_paths=[" documents/report.pdf ", "/documents/report.pdf/"],
    )

    assert [message.id for message in human_messages] == ["user-1", "user-2"]
    assert [message.content for message in human_messages] == [
        "Hello world",
        "Second message",
    ]
    assert human_messages[0].additional_kwargs == {
        "created_at": "2026-04-21T17:00:00+00:00",
        "context_file_paths": ["documents/report.pdf"],
    }
    assert human_messages[1].additional_kwargs == {
        "created_at": "2026-04-21T18:00:00+00:00",
        "context_file_paths": ["documents/report.pdf"],
    }


def test_build_transcript_messages_preserves_supported_roles(monkeypatch):
    """Visible transcript conversion should keep user and assistant turns."""
    monkeypatch.setattr("chat.submissions.iso_now", lambda: "2026-04-21T18:00:00+00:00")

    messages = [
        ChatStreamMessage(
            id="assistant-1",
            role="assistant",
            content="Earlier answer",
            additional_kwargs={"source": "history"},
        ),
        ChatStreamMessage(id="user-1", role="user", content="Follow-up"),
        ChatStreamMessage(id="tool-1", role="tool", content="Skip me"),
    ]

    transcript_messages = build_transcript_messages(
        messages,
        context_file_paths=[" docs/report.pdf "],
    )

    assert [message.id for message in transcript_messages] == [
        "assistant-1",
        "user-1",
    ]
    assert [message.content for message in transcript_messages] == [
        "Earlier answer",
        "Follow-up",
    ]
    assert transcript_messages[0].additional_kwargs == {
        "source": "history",
        "created_at": "2026-04-21T18:00:00+00:00",
    }
    assert transcript_messages[1].additional_kwargs == {
        "created_at": "2026-04-21T18:00:00+00:00",
        "context_file_paths": ["docs/report.pdf"],
    }
