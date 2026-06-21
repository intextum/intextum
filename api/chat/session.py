"""Request preparation and streaming helpers for chat generation."""

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import HTTPException, status

from chat.manager import ChatThreadManager
from chat.state import (
    ChatGraphInput,
    build_existing_thread_state_input,
    build_new_thread_state_input,
)
from chat.store import thread_config
from chat.stream import encode_sse_event
from chat.submissions import (
    build_human_messages,
    build_transcript_messages,
    derive_title_from_text,
)
from chat.time import iso_now
from chat.transport import ChatStreamServiceRequest

logger = logging.getLogger(__name__)

ChatStreamEventName = Literal["messages", "values"]


@dataclass
class PreparedChatStreamRun:
    """Prepared request-scoped state needed to run one LangGraph stream."""

    conversation_id: str
    thread_manager: ChatThreadManager
    graph_input: ChatGraphInput


@dataclass(frozen=True)
class ChatStreamEvent:
    """One supported LangGraph stream event that can be forwarded via SSE."""

    event: ChatStreamEventName
    data: Any


def parse_chat_stream_part(part: Any) -> ChatStreamEvent | None:
    """Filter a raw LangGraph stream item down to the event types we expose."""
    if not isinstance(part, dict):
        return None

    part_type = part.get("type")
    if part_type == "messages":
        return ChatStreamEvent(event="messages", data=part.get("data"))
    if part_type == "values":
        return ChatStreamEvent(event="values", data=part.get("data"))
    return None


async def prepare_chat_stream_run(
    *,
    thread_manager: ChatThreadManager,
    stream_request: ChatStreamServiceRequest,
    now: str | None = None,
    load_existing_snapshot: bool = True,
    use_full_transcript: bool = False,
) -> PreparedChatStreamRun:
    """Build the LangGraph input for one normalized chat stream request."""
    existing_snapshot = (
        await thread_manager.load_accessible_snapshot(stream_request.conversation_id)
        if load_existing_snapshot
        else None
    )

    submitted_messages = (
        build_transcript_messages(
            stream_request.messages,
            context_file_paths=thread_manager.context_file_paths,
        )
        if use_full_transcript
        else build_human_messages(
            stream_request.messages,
            context_file_paths=thread_manager.context_file_paths,
        )
    )
    if not submitted_messages:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="messages must include at least one user message",
        )
    if use_full_transcript and not any(
        getattr(message, "type", None) == "human" for message in submitted_messages
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="messages must include at least one user message",
        )

    resolved_now = now or iso_now()
    first_human_message = next(
        (
            message
            for message in submitted_messages
            if getattr(message, "type", None) == "human"
        ),
        submitted_messages[0],
    )
    if existing_snapshot is None:
        graph_input = build_new_thread_state_input(
            messages=submitted_messages,
            context_file_paths=thread_manager.context_file_paths,
            title=derive_title_from_text(str(first_human_message.content)),
            created_at=resolved_now,
            updated_at=resolved_now,
            user_sub=thread_manager.user_sub,
        )
    else:
        graph_input = build_existing_thread_state_input(
            messages=submitted_messages,
            context_file_paths=thread_manager.context_file_paths,
            updated_at=resolved_now,
        )

    return PreparedChatStreamRun(
        conversation_id=stream_request.conversation_id,
        thread_manager=thread_manager,
        graph_input=graph_input,
    )


async def iter_chat_stream_frames(
    prepared_run: PreparedChatStreamRun,
) -> AsyncIterator[str]:
    """Run the prepared LangGraph stream and yield SSE-encoded frames."""
    try:
        async for part in prepared_run.thread_manager.graph.astream(
            prepared_run.graph_input,
            config=thread_config(prepared_run.conversation_id),
            stream_mode=["messages", "values"],
            version="v2",
        ):
            # Let StreamingResponse propagate real client disconnects via task
            # cancellation; explicit request.is_disconnected() proved too eager
            # here and cancelled valid in-flight chat runs before the model reply.
            event = parse_chat_stream_part(part)
            if event is None:
                continue

            yield encode_sse_event(event.event, event.data)
    except asyncio.CancelledError:
        logger.info(
            "Chat stream cancelled for conversation %s",
            prepared_run.conversation_id,
        )
        return
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.exception(
            "Chat stream failed for conversation %s: %s",
            prepared_run.conversation_id,
            exc,
        )
        yield encode_sse_event(
            "error",
            {"name": "ChatStreamError", "message": "Chat generation failed."},
        )
