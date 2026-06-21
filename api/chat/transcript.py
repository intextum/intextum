"""Helpers for projecting persisted LangGraph state into conversation responses."""

from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage

from chat.snapshot import ChatThreadSnapshot
from chat.sources import parse_source_payloads
from chat.time import iso_now
from chat.transport import normalize_context_file_paths
from models.conversation import (
    ConversationDetail,
    ConversationMessage,
    ConversationSource,
    ConversationSummary,
)


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
            continue
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "".join(parts)


def _message_additional_kwargs(message: AnyMessage) -> dict[str, Any]:
    raw = getattr(message, "additional_kwargs", {}) or {}
    return raw if isinstance(raw, dict) else {}


def _message_context_paths(message: AnyMessage) -> list[str]:
    return normalize_context_file_paths(
        _message_additional_kwargs(message).get("context_file_paths")
    )


def _message_sources(message: AnyMessage) -> list[ConversationSource]:
    return parse_source_payloads(_message_additional_kwargs(message).get("sources"))


def _message_created_at(message: AnyMessage) -> str | None:
    created_at = _message_additional_kwargs(message).get("created_at")
    return created_at if isinstance(created_at, str) else None


def _message_metadata(message: AnyMessage) -> dict[str, Any] | None:
    metadata = _message_additional_kwargs(message).get("metadata")
    return metadata if isinstance(metadata, dict) else None


def _is_visible_message(message: AnyMessage) -> bool:
    if isinstance(message, HumanMessage):
        return True
    if isinstance(message, AIMessage):
        if getattr(message, "tool_calls", None):
            return False
        return not (
            not _message_text(message.content).strip()
            and not _message_sources(message)
            and not _message_metadata(message)
        )
    return False


def serialize_visible_messages(messages: list[AnyMessage]) -> list[ConversationMessage]:
    """Convert LangGraph messages into the UI chat transcript."""
    serialized: list[ConversationMessage] = []

    for message in messages:
        if not _is_visible_message(message):
            continue

        role = "assistant" if isinstance(message, AIMessage) else "user"
        metadata = None
        if role == "user":
            context_paths = _message_context_paths(message)
            metadata = {"context_file_paths": context_paths} if context_paths else None
        else:
            metadata = _message_metadata(message)

        serialized.append(
            ConversationMessage(
                id=str(getattr(message, "id", None) or uuid4()),
                role=role,
                content=_message_text(message.content),
                sources=_message_sources(message),
                metadata=metadata,
                created_at=_message_created_at(message),
                status=None,
            )
        )

    return serialized


def build_conversation_detail(
    thread_id: str,
    snapshot: ChatThreadSnapshot,
    *,
    title: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> ConversationDetail:
    """Build a conversation detail payload from thread state."""
    return ConversationDetail(
        id=thread_id,
        title=title if title is not None else snapshot.title,
        created_at=created_at or snapshot.created_at or iso_now(),
        updated_at=updated_at or snapshot.updated_at or iso_now(),
        messages=serialize_visible_messages(snapshot.messages),
        context_file_paths=list(snapshot.context_file_paths),
    )


def build_conversation_summary(
    thread_id: str,
    snapshot: ChatThreadSnapshot,
    *,
    updated_at: str | None = None,
    active_run_status: str | None = None,
) -> ConversationSummary:
    """Build a conversation summary payload from thread state."""
    return ConversationSummary(
        id=thread_id,
        title=snapshot.title,
        created_at=snapshot.created_at or iso_now(),
        updated_at=updated_at or snapshot.updated_at or iso_now(),
        active_run_status=active_run_status,
    )
