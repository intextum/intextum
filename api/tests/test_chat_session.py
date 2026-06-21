"""Tests for chat stream request preparation and event iteration."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessageChunk, HumanMessage

from chat.session import (
    ChatStreamEvent,
    iter_chat_stream_frames,
    parse_chat_stream_part,
    prepare_chat_stream_run,
)
from chat.snapshot import ChatThreadSnapshot
from chat.transport import ChatStreamServiceRequest
from models.chat import ChatStreamMessage


def _event_payload(frame: str):
    for line in frame.splitlines():
        if line.startswith("data: "):
            return json.loads(line.removeprefix("data: "))
    raise AssertionError("SSE frame did not contain a data line")


def _build_stream_request(
    *,
    content: str = " Hello ",
    conversation_id: str = "thread-1",
    created_at: str = "2026-04-21T18:00:00+00:00",
):
    return ChatStreamServiceRequest(
        conversation_id=conversation_id,
        messages=[
            ChatStreamMessage(
                id="user-1",
                type="human",
                content=content,
                created_at=created_at,
            )
        ],
        context_file_paths=["documents/report.pdf"],
    )


@pytest.mark.asyncio
async def test_prepare_chat_stream_run_builds_new_thread_input():
    """New-thread prep should include title, ownership, and creation timestamps."""
    thread_manager = SimpleNamespace(
        context_file_paths=["documents/report.pdf"],
        user_sub="sub-testuser",
        load_accessible_snapshot=AsyncMock(return_value=None),
    )

    prepared = await prepare_chat_stream_run(
        thread_manager=thread_manager,
        stream_request=_build_stream_request(),
        now="2026-04-21T18:00:00+00:00",
    )

    thread_manager.load_accessible_snapshot.assert_awaited_once_with("thread-1")
    assert prepared.conversation_id == "thread-1"
    assert prepared.thread_manager is thread_manager
    assert prepared.graph_input["title"] == "Hello"
    assert prepared.graph_input["created_at"] == "2026-04-21T18:00:00+00:00"
    assert prepared.graph_input["updated_at"] == "2026-04-21T18:00:00+00:00"
    assert prepared.graph_input["user_sub"] == "sub-testuser"
    assert prepared.graph_input["context_file_paths"] == ["documents/report.pdf"]
    assert [message.content for message in prepared.graph_input["messages"]] == [
        " Hello "
    ]


@pytest.mark.asyncio
async def test_prepare_chat_stream_run_builds_existing_thread_input():
    """Existing-thread prep should only update runtime fields."""
    thread_manager = SimpleNamespace(
        context_file_paths=["documents/report.pdf"],
        user_sub="sub-testuser",
        load_accessible_snapshot=AsyncMock(return_value=ChatThreadSnapshot()),
    )

    prepared = await prepare_chat_stream_run(
        thread_manager=thread_manager,
        stream_request=_build_stream_request(content="Follow up"),
        now="2026-04-21T18:00:00+00:00",
    )

    assert prepared.graph_input == {
        "messages": [
            HumanMessage(
                id="user-1",
                content="Follow up",
                additional_kwargs={
                    "created_at": "2026-04-21T18:00:00+00:00",
                    "context_file_paths": ["documents/report.pdf"],
                },
            )
        ],
        "context_file_paths": ["documents/report.pdf"],
        "updated_at": "2026-04-21T18:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_prepare_chat_stream_run_rejects_requests_without_user_messages():
    """Stream prep should fail when the normalized request has no user messages."""
    thread_manager = SimpleNamespace(
        context_file_paths=["documents/report.pdf"],
        user_sub="sub-testuser",
        load_accessible_snapshot=AsyncMock(return_value=None),
    )
    stream_request = ChatStreamServiceRequest(
        conversation_id="thread-1",
        messages=[ChatStreamMessage(id="assistant-1", type="ai", content="skip")],
        context_file_paths=["documents/report.pdf"],
    )

    with pytest.raises(HTTPException) as exc_info:
        await prepare_chat_stream_run(
            thread_manager=thread_manager,
            stream_request=stream_request,
            now="2026-04-21T18:00:00+00:00",
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "messages must include at least one user message"


@pytest.mark.asyncio
async def test_prepare_transient_chat_stream_uses_full_transcript_without_loading_snapshot():
    """Transient document chat should preserve assistant history and skip persistence lookup."""
    thread_manager = SimpleNamespace(
        context_file_paths=["documents/report.pdf"],
        user_sub="sub-testuser",
        load_accessible_snapshot=AsyncMock(return_value=ChatThreadSnapshot()),
    )
    stream_request = ChatStreamServiceRequest(
        conversation_id="thread-1",
        messages=[
            ChatStreamMessage(id="user-1", type="human", content="Summarize"),
            ChatStreamMessage(
                id="assistant-1",
                type="ai",
                content="Summary [1]",
                additional_kwargs={
                    "sources": [
                        {
                            "file_path": "documents/report.pdf",
                            "citation_index": 1,
                            "doc_refs": ["ref-1"],
                        }
                    ]
                },
            ),
            ChatStreamMessage(id="user-2", type="human", content="What changed?"),
        ],
        context_file_paths=["documents/report.pdf"],
    )

    prepared = await prepare_chat_stream_run(
        thread_manager=thread_manager,
        stream_request=stream_request,
        now="2026-04-21T18:00:00+00:00",
        load_existing_snapshot=False,
        use_full_transcript=True,
    )

    thread_manager.load_accessible_snapshot.assert_not_awaited()
    graph_messages = prepared.graph_input["messages"]
    assert [message.content for message in graph_messages] == [
        "Summarize",
        "Summary [1]",
        "What changed?",
    ]
    assert graph_messages[1].additional_kwargs["sources"][0]["doc_refs"] == ["ref-1"]
    assert prepared.graph_input["context_file_paths"] == ["documents/report.pdf"]


def test_parse_chat_stream_part_keeps_only_supported_event_types():
    """Only messages/values stream items should flow through the SSE adapter."""
    assert parse_chat_stream_part({"type": "messages", "data": "hello"}) == (
        ChatStreamEvent(
            event="messages",
            data="hello",
        )
    )
    assert parse_chat_stream_part({"type": "values", "data": {"ok": True}}) == (
        ChatStreamEvent(
            event="values",
            data={"ok": True},
        )
    )
    assert parse_chat_stream_part({"type": "updates", "data": "skip"}) is None
    assert parse_chat_stream_part("not-a-dict") is None


@pytest.mark.asyncio
async def test_iter_chat_stream_frames_filters_and_encodes_supported_events():
    """Stream iteration should ignore unsupported parts and SSE-encode supported ones."""

    async def fake_astream(*args, **kwargs):
        _ = args, kwargs
        yield "not-a-dict"
        yield {"type": "updates", "data": "skip"}
        yield {
            "type": "messages",
            "data": (
                AIMessageChunk(content="hello", id="ai-1"),
                {"langgraph_checkpoint_ns": "chatbot:root"},
            ),
        }
        yield {"type": "values", "data": {"updated_at": "2026-04-21T16:00:00+00:00"}}

    graph = SimpleNamespace(astream=fake_astream)
    prepared = SimpleNamespace(
        conversation_id="thread-1",
        graph_input={"messages": []},
        thread_manager=SimpleNamespace(graph=graph),
    )

    frames = [frame async for frame in iter_chat_stream_frames(prepared)]

    assert len(frames) == 2
    assert _event_payload(frames[0]) == [
        {
            "content": "hello",
            "additional_kwargs": {},
            "response_metadata": {},
            "type": "AIMessageChunk",
            "name": None,
            "id": "ai-1",
            "tool_calls": [],
            "invalid_tool_calls": [],
            "usage_metadata": None,
            "tool_call_chunks": [],
            "chunk_position": None,
        },
        {"langgraph_checkpoint_ns": "chatbot:root"},
    ]
    assert _event_payload(frames[1]) == {"updated_at": "2026-04-21T16:00:00+00:00"}


@pytest.mark.asyncio
async def test_iter_chat_stream_frames_emits_error_event_on_failure():
    """Unexpected stream failures should become one ChatStreamError SSE frame."""

    async def failing_astream(*args, **kwargs):
        _ = args, kwargs
        raise RuntimeError("boom")
        yield  # pragma: no cover

    graph = SimpleNamespace(astream=failing_astream)
    prepared = SimpleNamespace(
        conversation_id="thread-1",
        graph_input={"messages": []},
        thread_manager=SimpleNamespace(graph=graph),
    )

    frames = [frame async for frame in iter_chat_stream_frames(prepared)]

    assert len(frames) == 1
    assert _event_payload(frames[0]) == {
        "name": "ChatStreamError",
        "message": "Chat generation failed.",
    }
