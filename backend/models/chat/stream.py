"""Chat request models."""

from typing import Any

from pydantic import BaseModel, Field

from models.enums import ConversationRunMode


class ChatStreamConfigurable(BaseModel):
    """Subset of LangGraph-style configurable values we currently support."""

    thread_id: str


class ChatStreamConfig(BaseModel):
    """Optional execution config forwarded by the frontend stream hook."""

    configurable: ChatStreamConfigurable


class ChatStreamMessage(BaseModel):
    """Minimal message payload accepted by the custom LangGraph stream route."""

    id: str | None = None
    type: str | None = None
    role: str | None = None
    content: Any = None
    created_at: str | None = None
    additional_kwargs: dict[str, Any] = Field(default_factory=dict)

    def resolved_created_at(self) -> str | None:
        """Return message creation time from the top-level or additional kwargs."""
        if isinstance(self.created_at, str):
            return self.created_at
        created_at = self.additional_kwargs.get("created_at")
        return created_at if isinstance(created_at, str) else None


class ChatStreamInput(BaseModel):
    """Conversation state sent by the frontend chat stream."""

    messages: list[ChatStreamMessage] = Field(default_factory=list)
    context_file_paths: list[str] = Field(default_factory=list)
    mode: ConversationRunMode = ConversationRunMode.CHAT


class ChatStreamRequest(BaseModel):
    """Custom transport payload used by LangGraph's ``useStream`` hook."""

    input: ChatStreamInput
    config: ChatStreamConfig
    context: dict[str, Any] | None = None
    command: dict[str, Any] | None = None
