"""Tests for projecting LangGraph state into conversation API models."""

from langchain_core.messages import AIMessage, HumanMessage

from chat.snapshot import ChatThreadSnapshot
from chat.transcript import build_conversation_detail, serialize_visible_messages


def test_serialize_visible_messages_keeps_user_context_and_assistant_sources():
    """Visible transcript messages should preserve normalized metadata and citations."""
    messages = [
        HumanMessage(
            id="human-1",
            content="Hello",
            additional_kwargs={
                "created_at": "2026-04-21T17:00:00+00:00",
                "context_file_paths": [
                    " documents/report.pdf ",
                    "/documents/report.pdf/",
                ],
            },
        ),
        AIMessage(id="ai-empty", content=""),
        AIMessage(
            id="ai-1",
            content="Answer",
            additional_kwargs={
                "created_at": "2026-04-21T18:00:00+00:00",
                "sources": [
                    {
                        "file_path": "documents/report.pdf",
                        "title": "report.pdf",
                        "page_numbers": [1, 2],
                        "doc_refs": ["ref-1"],
                        "images": ["https://example.invalid/page-1.png"],
                        "citation_index": 1,
                        "quote": "Quoted text",
                    }
                ],
            },
        ),
    ]

    serialized = serialize_visible_messages(messages)

    assert [message.id for message in serialized] == ["human-1", "ai-1"]
    assert serialized[0].metadata == {"context_file_paths": ["documents/report.pdf"]}
    assert serialized[0].created_at == "2026-04-21T17:00:00+00:00"
    assert serialized[1].sources[0].file_path == "documents/report.pdf"
    assert serialized[1].sources[0].page_numbers == [1, 2]
    assert serialized[1].sources[0].images == ["https://example.invalid/page-1.png"]
    assert serialized[1].created_at == "2026-04-21T18:00:00+00:00"


def test_build_conversation_detail_uses_iso_fallbacks(monkeypatch):
    """Conversation projection should fill missing top-level timestamps consistently."""
    monkeypatch.setattr("chat.transcript.iso_now", lambda: "2026-04-21T19:00:00+00:00")

    detail = build_conversation_detail(
        "thread-1",
        ChatThreadSnapshot(messages=[HumanMessage(id="human-1", content="Hello")]),
    )

    assert detail.id == "thread-1"
    assert detail.title is None
    assert detail.created_at == "2026-04-21T19:00:00+00:00"
    assert detail.updated_at == "2026-04-21T19:00:00+00:00"
    assert [message.id for message in detail.messages] == ["human-1"]
