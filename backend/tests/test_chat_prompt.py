"""Tests for chat prompt composition."""

from types import SimpleNamespace

from chat.context import ChatContextScope
from chat.prompt import build_system_prompt


def _runtime(*, context_scope: ChatContextScope | None = None):
    return SimpleNamespace(
        settings=SimpleNamespace(
            CHAT_SYSTEM_PROMPT="Base system prompt.",
            CHAT_TOOL_PROMPT="Tool prompt.",
        ),
        context_scope=context_scope or ChatContextScope(),
    )


def test_build_system_prompt_includes_conversation_history_guidance():
    prompt = build_system_prompt(_runtime())

    assert (
        "Conversation history in this thread is part of the available context."
        in prompt
    )
    assert "deep research reports generated in this thread are valid context" in prompt
    assert "Do not claim information is missing from documents" in prompt


def test_build_system_prompt_keeps_context_scope_restrictions():
    prompt = build_system_prompt(
        _runtime(
            context_scope=ChatContextScope(
                raw_paths=["docs/report.pdf"],
                constraints=[("docs/report.pdf", "folder-1", "report.pdf")],
                folder_name_to_uuid={"docs": "folder-1"},
                folder_uuid_to_name={"folder-1": "docs"},
            )
        )
    )

    assert (
        "Conversation history in this thread is part of the available context."
        in prompt
    )
    assert "Restrict all tool calls to these files:" in prompt
    assert "- docs/report.pdf" in prompt
