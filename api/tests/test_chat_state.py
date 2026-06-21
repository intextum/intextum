"""Tests for typed chat state builders."""

from langchain_core.messages import AIMessage, HumanMessage

from chat.state import (
    ChatThreadStatePatch,
    build_existing_thread_state_input,
    build_new_thread_state_input,
    build_title_state_update,
)


def test_build_existing_thread_state_input_only_sets_runtime_fields():
    """Existing-thread inputs should not overwrite creation or ownership fields."""
    messages = [HumanMessage(content="Hello", id="msg-1")]

    payload = build_existing_thread_state_input(
        messages=messages,
        context_file_paths=["documents/report.pdf"],
        updated_at="2026-04-21T18:00:00+00:00",
    )

    assert payload == {
        "messages": messages,
        "context_file_paths": ["documents/report.pdf"],
        "updated_at": "2026-04-21T18:00:00+00:00",
    }


def test_build_new_thread_state_input_sets_full_initial_state():
    """New-thread inputs should include title, timestamps, and ownership."""
    messages = [HumanMessage(content="Hello", id="msg-1")]

    payload = build_new_thread_state_input(
        messages=messages,
        context_file_paths=["documents/report.pdf"],
        title=None,
        created_at="2026-04-21T18:00:00+00:00",
        updated_at="2026-04-21T18:00:00+00:00",
        user_sub="sub-testuser",
    )

    assert payload == {
        "messages": messages,
        "context_file_paths": ["documents/report.pdf"],
        "title": None,
        "created_at": "2026-04-21T18:00:00+00:00",
        "updated_at": "2026-04-21T18:00:00+00:00",
        "user_sub": "sub-testuser",
    }


def test_build_title_state_update_preserves_null_titles():
    """Rename patches should keep explicit null titles instead of dropping them."""
    patch = build_title_state_update(
        title=None,
        updated_at="2026-04-21T18:00:00+00:00",
    )

    assert patch == ChatThreadStatePatch(
        title=None,
        updated_at="2026-04-21T18:00:00+00:00",
    )
    assert patch.to_state_update() == {
        "title": None,
        "updated_at": "2026-04-21T18:00:00+00:00",
    }


def test_chat_thread_state_patch_omits_unset_fields():
    """State patches should serialize only the fields that were explicitly set."""
    patch = ChatThreadStatePatch(updated_at="2026-04-21T18:00:00+00:00")

    assert patch.to_state_update() == {
        "updated_at": "2026-04-21T18:00:00+00:00",
    }


def test_chat_thread_state_patch_preserves_langchain_message_objects():
    """Manual state patches should keep LangChain messages as message instances."""
    messages = [
        HumanMessage(content="Question", id="msg-user-1"),
        AIMessage(content="Answer", id="msg-ai-1"),
    ]
    patch = ChatThreadStatePatch(
        messages=messages,
        updated_at="2026-04-21T18:00:00+00:00",
    )

    state_update = patch.to_state_update()

    assert len(state_update["messages"]) == 2
    assert isinstance(state_update["messages"][0], HumanMessage)
    assert isinstance(state_update["messages"][1], AIMessage)
    assert state_update["messages"][0].content == "Question"
    assert state_update["messages"][1].content == "Answer"
