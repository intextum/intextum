"""Tests for typed chat transport models."""

from models.chat import ChatStreamMessage


def test_chat_stream_message_resolves_created_at_from_additional_kwargs():
    """Created-at fallback should read the transport's additional kwargs field."""
    message = ChatStreamMessage(
        id="msg-1",
        type="human",
        content="Hello world",
        additional_kwargs={"created_at": "2026-04-21T18:00:00+00:00"},
    )

    assert message.resolved_created_at() == "2026-04-21T18:00:00+00:00"


def test_chat_stream_message_prefers_top_level_created_at():
    """Top-level created_at should override any value inside additional kwargs."""
    message = ChatStreamMessage(
        id="msg-1",
        type="human",
        content="Hello world",
        created_at="2026-04-21T19:00:00+00:00",
        additional_kwargs={"created_at": "2026-04-21T18:00:00+00:00"},
    )

    assert message.resolved_created_at() == "2026-04-21T19:00:00+00:00"
