"""Helpers for shaping submitted UI chat messages into LangChain messages."""

from uuid import uuid4

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage

from chat.time import iso_now
from chat.transport import normalize_context_file_paths
from models.chat import ChatStreamMessage

HUMAN_MESSAGE_KINDS = {"human", "user", "humanmessagechunk"}
AI_MESSAGE_KINDS = {"ai", "assistant", "aimessagechunk"}


def derive_title_from_text(text: str) -> str | None:
    """Derive a short title from a user message."""
    stripped = text.strip()
    if not stripped:
        return None
    return stripped[:100]


def _text_content(message: ChatStreamMessage) -> str | None:
    content = message.content
    if not isinstance(content, str) or not content.strip():
        return None
    return content


def _message_kind(message: ChatStreamMessage) -> str:
    return str(message.type or message.role or "").lower()


def _message_id(message: ChatStreamMessage) -> str:
    return str(message.id or uuid4())


def _message_kwargs(
    message: ChatStreamMessage,
    *,
    context_file_paths: list[str] | None = None,
    preserve_existing: bool = False,
) -> dict[str, object]:
    additional_kwargs = (
        dict(message.additional_kwargs or {}) if preserve_existing else {}
    )
    additional_kwargs["created_at"] = message.resolved_created_at() or iso_now()
    if context_file_paths:
        additional_kwargs["context_file_paths"] = context_file_paths
    return additional_kwargs


def build_human_messages(
    messages: list[ChatStreamMessage],
    *,
    context_file_paths: list[str],
) -> list[HumanMessage]:
    """Convert submitted UI messages into LangGraph human messages."""
    normalized_context_paths = normalize_context_file_paths(context_file_paths)
    human_messages: list[HumanMessage] = []

    for message in messages:
        if _message_kind(message) not in HUMAN_MESSAGE_KINDS:
            continue

        content = _text_content(message)
        if content is None:
            continue

        human_messages.append(
            HumanMessage(
                id=_message_id(message),
                content=content,
                additional_kwargs=_message_kwargs(
                    message,
                    context_file_paths=normalized_context_paths,
                ),
            )
        )

    return human_messages


def build_transcript_messages(
    messages: list[ChatStreamMessage],
    *,
    context_file_paths: list[str],
) -> list[AnyMessage]:
    """Convert a submitted visible UI transcript into LangGraph messages."""
    normalized_context_paths = normalize_context_file_paths(context_file_paths)
    transcript_messages: list[AnyMessage] = []

    for message in messages:
        content = _text_content(message)
        if content is None:
            continue

        message_kind = _message_kind(message)
        additional_kwargs = _message_kwargs(
            message,
            context_file_paths=(
                normalized_context_paths
                if message_kind in HUMAN_MESSAGE_KINDS
                else None
            ),
            preserve_existing=True,
        )

        if message_kind in HUMAN_MESSAGE_KINDS:
            transcript_messages.append(
                HumanMessage(
                    id=_message_id(message),
                    content=content,
                    additional_kwargs=additional_kwargs,
                )
            )
            continue

        if message_kind in AI_MESSAGE_KINDS:
            transcript_messages.append(
                AIMessage(
                    id=_message_id(message),
                    content=content,
                    additional_kwargs=additional_kwargs,
                )
            )

    return transcript_messages
