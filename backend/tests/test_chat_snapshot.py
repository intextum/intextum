"""Tests for typed LangGraph thread snapshot parsing."""

from langchain_core.messages import AIMessage, HumanMessage

from chat.snapshot import ChatThreadSnapshot


def test_chat_thread_snapshot_parses_typed_state_fields():
    """Raw LangGraph values should be normalized into a typed snapshot."""
    snapshot = ChatThreadSnapshot.from_state_values(
        {
            "title": "Example",
            "created_at": "2026-04-21T18:00:00+00:00",
            "updated_at": "2026-04-21T19:00:00+00:00",
            "user_sub": "sub-testuser",
            "messages": [
                HumanMessage(id="human-1", content="Hello"),
                "skip-me",
                AIMessage(id="ai-1", content="World"),
            ],
            "context_file_paths": [" documents/report.pdf ", "/documents/report.pdf/"],
        }
    )

    assert snapshot == ChatThreadSnapshot(
        title="Example",
        created_at="2026-04-21T18:00:00+00:00",
        updated_at="2026-04-21T19:00:00+00:00",
        user_sub="sub-testuser",
        messages=[
            HumanMessage(id="human-1", content="Hello"),
            AIMessage(id="ai-1", content="World"),
        ],
        context_file_paths=["documents/report.pdf"],
    )
