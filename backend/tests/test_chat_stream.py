"""Regression tests for LangGraph SSE stream encoding."""

import json

from langchain_core.messages import AIMessageChunk, HumanMessage

from chat.stream import encode_sse_event


def _event_payload(frame: str):
    for line in frame.splitlines():
        if line.startswith("data: "):
            return json.loads(line.removeprefix("data: "))
    raise AssertionError("SSE frame did not contain a data line")


def test_encode_sse_event_serializes_message_tuple():
    """Messages stream events should serialize LangChain chunks for the JS client."""
    frame = encode_sse_event(
        "messages",
        (
            AIMessageChunk(content="hello", id="ai-1"),
            {"langgraph_checkpoint_ns": "chatbot:root"},
        ),
    )

    payload = _event_payload(frame)
    assert payload == [
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


def test_encode_sse_event_serializes_nested_values_messages():
    """Values events should serialize nested LangChain messages in state snapshots."""
    frame = encode_sse_event(
        "values",
        {
            "messages": [HumanMessage(content="hello", id="human-1")],
            "updated_at": "2026-04-21T16:00:00+00:00",
        },
    )

    payload = _event_payload(frame)
    assert payload == {
        "messages": [
            {
                "content": "hello",
                "additional_kwargs": {},
                "response_metadata": {},
                "type": "human",
                "name": None,
                "id": "human-1",
            }
        ],
        "updated_at": "2026-04-21T16:00:00+00:00",
    }
