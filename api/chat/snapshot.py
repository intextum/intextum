"""Typed view over persisted LangGraph thread state."""

from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import BaseMessage

from chat.transport import normalize_context_file_paths


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


@dataclass(frozen=True)
class ChatThreadSnapshot:
    """Parsed thread state used across LangGraph chat persistence helpers."""

    title: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    user_sub: str | None = None
    messages: list[BaseMessage] = field(default_factory=list)
    context_file_paths: list[str] = field(default_factory=list)

    @classmethod
    def from_state_values(cls, values: Any) -> "ChatThreadSnapshot":
        """Build a typed snapshot from raw LangGraph state values."""
        data = values if isinstance(values, dict) else {}
        raw_messages = data.get("messages")

        return cls(
            title=_optional_string(data.get("title")),
            created_at=_optional_string(data.get("created_at")),
            updated_at=_optional_string(data.get("updated_at")),
            user_sub=_optional_string(data.get("user_sub")),
            messages=[
                message for message in raw_messages if isinstance(message, BaseMessage)
            ]
            if isinstance(raw_messages, list)
            else [],
            context_file_paths=normalize_context_file_paths(
                data.get("context_file_paths")
            ),
        )
