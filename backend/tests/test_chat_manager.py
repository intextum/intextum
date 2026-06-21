"""Tests for shared LangGraph thread lifecycle management."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from chat.manager import ChatThreadManager
from chat.snapshot import ChatThreadSnapshot
from models.ai_settings import EffectiveAiSettings
from models.user import User


def test_chat_thread_manager_builds_graph_once_with_normalized_context_paths():
    """The manager should normalize context once and lazily build one graph."""
    user = User(username="testuser", sub="sub-testuser")
    mock_db = AsyncMock()
    mock_graph = MagicMock()

    with patch(
        "chat.manager.build_request_scoped_chat_graph",
        return_value=mock_graph,
    ) as build_graph:
        manager = ChatThreadManager(
            db=mock_db,
            user=user,
            context_file_paths=[" documents/report.pdf ", "/documents/report.pdf/"],
        )

        assert manager.context_file_paths == ["documents/report.pdf"]
        assert manager.graph is mock_graph
        assert manager.graph is mock_graph

    build_graph.assert_called_once_with(
        db=mock_db,
        user=user,
        context_file_paths=["documents/report.pdf"],
        ai_settings=None,
        persist_checkpoints=True,
    )


def test_chat_thread_manager_forwards_effective_ai_settings_to_graph_builder():
    """The manager should pass request-scoped AI overrides into the graph builder."""
    user = User(username="testuser", sub="sub-testuser")
    mock_db = AsyncMock()
    mock_graph = MagicMock()
    ai_settings = EffectiveAiSettings(
        chat_model="admin-chat-model",
        chat_system_prompt="System prompt",
        chat_tool_prompt="Tool prompt",
        chat_search_limit=7,
        chat_document_max_chars=25000,
        picture_description_model="vlm-model",
        picture_description_prompt="Describe the image.",
    )

    with patch(
        "chat.manager.build_request_scoped_chat_graph",
        return_value=mock_graph,
    ) as build_graph:
        manager = ChatThreadManager(
            db=mock_db,
            user=user,
            context_file_paths=[],
            ai_settings=ai_settings,
        )

        assert manager.graph is mock_graph

    build_graph.assert_called_once_with(
        db=mock_db,
        user=user,
        context_file_paths=[],
        ai_settings=ai_settings,
        persist_checkpoints=True,
    )


def test_chat_thread_manager_load_accessible_values_raises_for_foreign_thread():
    """Accessible loads should reject existing threads owned by another user."""

    async def run_test():
        user = User(username="testuser", sub="sub-testuser")
        manager = ChatThreadManager(db=AsyncMock(), user=user, context_file_paths=[])
        manager._graph_thread_store = AsyncMock()
        manager._graph_thread_store.load_snapshot.return_value = ChatThreadSnapshot(
            user_sub="other-user"
        )

        with pytest.raises(HTTPException) as exc_info:
            await manager.load_accessible_snapshot("thread-1")

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Conversation not found"

    asyncio.run(run_test())


def test_chat_thread_manager_load_owned_values_returns_none_for_foreign_thread():
    """Owned loads should quietly hide threads that belong to another user."""

    async def run_test():
        user = User(username="testuser", sub="sub-testuser")
        manager = ChatThreadManager(db=AsyncMock(), user=user, context_file_paths=[])
        manager._graph_thread_store = AsyncMock()
        manager._graph_thread_store.load_snapshot.return_value = ChatThreadSnapshot(
            user_sub="other-user"
        )

        assert await manager.load_owned_snapshot("thread-1") is None

    asyncio.run(run_test())


def test_chat_thread_manager_iter_owned_thread_values_deduplicates_and_filters():
    """Listing owned values should skip duplicates and foreign threads."""

    async def run_test():
        user = User(username="testuser", sub="sub-testuser")
        manager = ChatThreadManager(db=AsyncMock(), user=user, context_file_paths=[])

        checkpoints = [
            {
                "config": {"configurable": {"thread_id": "thread-1"}},
                "checkpoint": {
                    "channel_values": {"user_sub": "sub-testuser", "title": "First"}
                },
            },
            {
                "config": {"configurable": {"thread_id": "thread-1"}},
                "checkpoint": {
                    "channel_values": {"user_sub": "sub-testuser", "title": "Duplicate"}
                },
            },
            {
                "config": {"configurable": {"thread_id": "thread-2"}},
                "checkpoint": {
                    "channel_values": {"user_sub": "other-user", "title": "Hidden"}
                },
            },
            {
                "config": {"configurable": {"thread_id": "thread-3"}},
                "checkpoint": {
                    "channel_values": {"user_sub": "sub-testuser", "title": "Visible"}
                },
            },
        ]

        async def iter_checkpoints(*, limit=None):
            assert limit == 10
            for checkpoint in checkpoints:
                yield checkpoint

        manager._checkpoint_store = MagicMock()
        manager._checkpoint_store.list_checkpoints = iter_checkpoints

        collected = [
            item async for item in manager.iter_owned_thread_snapshots(limit=10)
        ]

        assert collected == [
            (
                "thread-1",
                ChatThreadSnapshot(user_sub="sub-testuser", title="First"),
            ),
            (
                "thread-3",
                ChatThreadSnapshot(user_sub="sub-testuser", title="Visible"),
            ),
        ]

    asyncio.run(run_test())
