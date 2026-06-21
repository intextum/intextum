"""Tests for chat transport parsing and normalization."""

import pytest
from fastapi import HTTPException

from chat.transport import (
    ChatStreamServiceRequest,
    normalize_context_file_paths,
    validate_stream_request,
)
from models.chat import ChatStreamMessage


def test_normalize_context_file_paths_deduplicates_and_trims():
    """Context file paths should be normalized once for tool scoping."""
    assert normalize_context_file_paths(
        [
            " documents/report.pdf ",
            "/documents/report.pdf/",
            "",
            1,
            "documents/other.pdf",
        ]
    ) == ["documents/report.pdf", "documents/other.pdf"]


def test_validate_stream_request_normalizes_and_extracts_fields():
    """Validated stream requests should expose the service-ready shape."""
    parsed = validate_stream_request(
        {
            "input": {
                "messages": [
                    {
                        "id": "msg-1",
                        "type": "human",
                        "content": "Hello world",
                    }
                ],
                "context_file_paths": [" docs/report.pdf ", "/docs/report.pdf/"],
            },
            "config": {"configurable": {"thread_id": "thread-1"}},
        }
    )

    assert parsed == ChatStreamServiceRequest(
        conversation_id="thread-1",
        messages=[
            ChatStreamMessage(
                id="msg-1",
                type="human",
                content="Hello world",
            )
        ],
        context_file_paths=["docs/report.pdf"],
    )


def test_validate_stream_request_rejects_commands():
    """Command payloads should be rejected until command handling exists."""
    with pytest.raises(HTTPException) as exc_info:
        validate_stream_request(
            {
                "input": {
                    "messages": [{"id": "msg-1", "type": "human", "content": "Hi"}],
                    "context_file_paths": [],
                },
                "config": {"configurable": {"thread_id": "thread-1"}},
                "command": {"resume": "ignored"},
            }
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Streaming commands are not supported"


def test_validate_stream_request_requires_messages():
    """Empty message stacks should fail validation before hitting the service."""
    with pytest.raises(HTTPException) as exc_info:
        validate_stream_request(
            {
                "input": {"messages": [], "context_file_paths": []},
                "config": {"configurable": {"thread_id": "thread-1"}},
            }
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "messages must not be empty"
