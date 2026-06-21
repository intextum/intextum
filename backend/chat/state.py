"""LangGraph state definitions for the chat workflow."""

from typing import Annotated, TypedDict, cast

from langchain_core.messages import AnyMessage, RemoveMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict


class ChatGraphState(TypedDict):
    """Minimal state carried through the graph."""

    messages: Annotated[list[AnyMessage], add_messages]
    context_file_paths: list[str]
    title: str | None
    created_at: str
    updated_at: str
    user_sub: str


class ChatGraphStateUpdate(TypedDict, total=False):
    """Partial LangGraph state patch used for manual updates and inputs."""

    messages: list[AnyMessage]
    context_file_paths: list[str]
    title: str | None
    created_at: str
    updated_at: str
    user_sub: str


ChatGraphInput = ChatGraphState | ChatGraphStateUpdate


class ChatThreadStatePatch(BaseModel):
    """Typed partial state patch used for manual LangGraph updates."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    messages: list[AnyMessage | RemoveMessage] | None = None
    context_file_paths: list[str] | None = None
    title: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    user_sub: str | None = None

    def to_state_update(self) -> ChatGraphStateUpdate:
        """Convert this patch into the dict shape expected by LangGraph."""
        update: dict[str, object] = {}
        for field_name in (
            "messages",
            "context_file_paths",
            "title",
            "created_at",
            "updated_at",
            "user_sub",
        ):
            if field_name in self.model_fields_set:
                update[field_name] = getattr(self, field_name)
        return cast(ChatGraphStateUpdate, update)


def build_existing_thread_state_input(
    *,
    messages: list[AnyMessage],
    context_file_paths: list[str],
    updated_at: str,
) -> ChatGraphStateUpdate:
    """Build the graph input used when continuing an existing thread."""
    return {
        "messages": messages,
        "context_file_paths": context_file_paths,
        "updated_at": updated_at,
    }


def build_new_thread_state_input(
    *,
    messages: list[AnyMessage],
    context_file_paths: list[str],
    title: str | None,
    created_at: str,
    updated_at: str,
    user_sub: str,
) -> ChatGraphState:
    """Build the initial graph state for a brand-new thread."""
    return {
        "messages": messages,
        "context_file_paths": context_file_paths,
        "title": title,
        "created_at": created_at,
        "updated_at": updated_at,
        "user_sub": user_sub,
    }


def build_title_state_update(
    *, title: str | None, updated_at: str
) -> ChatThreadStatePatch:
    """Build the manual state patch used when renaming a thread."""
    return ChatThreadStatePatch(title=title, updated_at=updated_at)
