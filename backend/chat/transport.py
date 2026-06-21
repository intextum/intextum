"""Helpers for parsing the custom chat stream transport payload."""

import json
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, status
from pydantic import ValidationError

from models.chat import ChatStreamMessage, ChatStreamRequest
from models.enums import ConversationRunMode

MAX_CHAT_PAYLOAD_BYTES = 1_000_000


@dataclass(frozen=True)
class ChatStreamServiceRequest:
    """Normalized chat stream request forwarded into the streaming service."""

    conversation_id: str
    messages: list[ChatStreamMessage]
    context_file_paths: list[str]
    mode: ConversationRunMode = ConversationRunMode.CHAT


def normalize_context_file_paths(raw_paths: Any) -> list[str]:
    """Normalize optional chat context file paths."""
    if not isinstance(raw_paths, list):
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_paths:
        if not isinstance(item, str):
            continue
        path = item.strip().strip("/")
        if not path or path in seen:
            continue
        seen.add(path)
        normalized.append(path)
    return normalized


def parse_chat_payload(body: bytes) -> Any:
    """Decode one raw chat transport payload."""
    if not body:
        return {}
    try:
        return json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid JSON payload",
        ) from e


async def read_request_body_limited(
    request: Request, *, max_bytes: int = MAX_CHAT_PAYLOAD_BYTES
) -> bytes:
    """Read request body with an explicit size ceiling."""
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"Payload too large. Max {max_bytes} bytes.",
                )
        except ValueError:
            pass

    body_chunks: list[bytes] = []
    total_bytes = 0
    async for chunk in request.stream():
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Payload too large. Max {max_bytes} bytes.",
            )
        body_chunks.append(chunk)
    return b"".join(body_chunks)


def validate_stream_request(payload: Any) -> ChatStreamServiceRequest:
    """Validate and normalize one decoded chat stream payload."""
    try:
        parsed = ChatStreamRequest.model_validate(payload)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=e.errors(),
        ) from e

    if parsed.command is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Streaming commands are not supported",
        )

    if not parsed.input.messages:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="messages must not be empty",
        )

    return ChatStreamServiceRequest(
        conversation_id=parsed.config.configurable.thread_id,
        messages=parsed.input.messages,
        context_file_paths=normalize_context_file_paths(
            parsed.input.context_file_paths
        ),
        mode=parsed.input.mode,
    )


async def parse_stream_request(request: Request) -> ChatStreamServiceRequest:
    """Parse the native LangGraph custom transport request payload."""
    body = await read_request_body_limited(request)
    return validate_stream_request(parse_chat_payload(body))
