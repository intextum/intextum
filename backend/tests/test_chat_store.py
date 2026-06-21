"""Tests for LangGraph thread persistence helpers."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch

from chat.snapshot import ChatThreadSnapshot
from chat.state import ChatThreadStatePatch
from chat.store import ChatThreadStore


def test_chat_thread_store_checkpoint_helpers_extract_typed_snapshot():
    """Checkpoint helper methods should extract typed metadata safely."""
    checkpoint = {
        "checkpoint": {
            "channel_values": {
                "title": "Example",
                "user_sub": "user-1",
                "context_file_paths": [" documents/report.pdf "],
            }
        },
        "config": {"configurable": {"thread_id": "thread-1"}},
    }

    assert ChatThreadStore.checkpoint_snapshot(checkpoint) == ChatThreadSnapshot(
        title="Example",
        user_sub="user-1",
        context_file_paths=["documents/report.pdf"],
    )
    assert ChatThreadStore.checkpoint_thread_id(checkpoint) == "thread-1"
    assert (
        ChatThreadStore.is_thread_owned_by_user(
            ChatThreadSnapshot(user_sub="user-1"),
            "user-1",
        )
        is True
    )
    assert (
        ChatThreadStore.is_thread_owned_by_user(
            ChatThreadSnapshot(user_sub="user-2"),
            "user-1",
        )
        is False
    )


def test_chat_thread_store_delete_thread_uses_checkpointer_api():
    """Deleting a thread should go through the LangGraph checkpointer API."""

    async def run_test():
        delete_thread = AsyncMock(return_value=None)
        store = ChatThreadStore(db=AsyncMock())

        with patch(
            "chat.store.get_chat_checkpointer",
            return_value=SimpleNamespace(adelete_thread=delete_thread),
        ):
            await store.delete_thread("thread-1")

        delete_thread.assert_awaited_once_with("thread-1")

    asyncio.run(run_test())


def test_chat_thread_store_delete_thread_falls_back_when_checkpointer_delete_is_unimplemented():
    """Deleting a thread should fall back to raw saver SQL when the saver has no delete API."""

    async def run_test():
        cursor = AsyncMock()

        @asynccontextmanager
        async def raw_cursor(*, pipeline=False):
            assert pipeline is True
            yield cursor

        delete_thread = AsyncMock(side_effect=NotImplementedError)
        store = ChatThreadStore(db=AsyncMock())

        with patch(
            "chat.store.get_chat_checkpointer",
            return_value=SimpleNamespace(
                adelete_thread=delete_thread,
                _cursor=raw_cursor,
            ),
        ):
            await store.delete_thread("thread-1")

        delete_thread.assert_awaited_once_with("thread-1")
        assert cursor.execute.await_args_list == [
            call("DELETE FROM checkpoint_writes WHERE thread_id = %s", ("thread-1",)),
            call("DELETE FROM checkpoint_blobs WHERE thread_id = %s", ("thread-1",)),
            call("DELETE FROM checkpoints WHERE thread_id = %s", ("thread-1",)),
        ]

    asyncio.run(run_test())


def test_chat_thread_store_update_state_serializes_patch():
    """Manual state updates should pass a serialized typed patch into LangGraph."""

    async def run_test():
        mock_graph = AsyncMock()
        store = ChatThreadStore(db=AsyncMock(), graph=mock_graph)

        await store.update_state(
            "thread-1",
            ChatThreadStatePatch(title=None, updated_at="2026-04-21T18:00:00+00:00"),
        )

        mock_graph.aupdate_state.assert_awaited_once_with(
            {"configurable": {"thread_id": "thread-1"}},
            {"title": None, "updated_at": "2026-04-21T18:00:00+00:00"},
            as_node=None,
        )

    asyncio.run(run_test())


def test_chat_thread_store_update_state_passes_as_node():
    """Manual state updates should forward an explicit LangGraph writer node."""

    async def run_test():
        mock_graph = AsyncMock()
        store = ChatThreadStore(db=AsyncMock(), graph=mock_graph)

        await store.update_state(
            "thread-1",
            ChatThreadStatePatch(updated_at="2026-04-21T18:00:00+00:00"),
            as_node="chatbot",
        )

        mock_graph.aupdate_state.assert_awaited_once_with(
            {"configurable": {"thread_id": "thread-1"}},
            {"updated_at": "2026-04-21T18:00:00+00:00"},
            as_node="chatbot",
        )

    asyncio.run(run_test())
