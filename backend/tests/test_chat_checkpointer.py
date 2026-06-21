"""Tests for LangGraph checkpointer lifecycle."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import chat.checkpointer as checkpointer_module


class _AsyncCheckpointerContext:
    def __init__(self, saver):
        self.saver = saver
        self.exit = AsyncMock(return_value=None)

    async def __aenter__(self):
        return self.saver

    async def __aexit__(self, exc_type, exc, tb):
        await self.exit(exc_type, exc, tb)
        return False


def test_init_chat_checkpointer_sets_up_schema_with_owner_url_then_uses_app_url():
    async def run_test():
        setup_saver = MagicMock()
        setup_saver.setup = AsyncMock()
        runtime_saver = MagicMock()
        setup_cm = _AsyncCheckpointerContext(setup_saver)
        runtime_cm = _AsyncCheckpointerContext(runtime_saver)

        checkpointer_module._checkpointer = None
        checkpointer_module._checkpointer_cm = None

        with (
            patch.object(
                checkpointer_module,
                "CHECKPOINTER_SETUP_DATABASE_URL",
                "owner-url",
            ),
            patch.object(
                checkpointer_module,
                "CHECKPOINTER_DATABASE_URL",
                "app-url",
            ),
            patch.object(
                checkpointer_module.AsyncShallowPostgresSaver,
                "from_conn_string",
                side_effect=[setup_cm, runtime_cm],
            ) as from_conn_string,
        ):
            await checkpointer_module.init_chat_checkpointer()

        assert from_conn_string.call_args_list == [
            call("owner-url"),
            call("app-url"),
        ]
        setup_saver.setup.assert_awaited_once()
        setup_cm.exit.assert_awaited_once_with(None, None, None)
        assert checkpointer_module.get_chat_checkpointer() is runtime_saver

        await checkpointer_module.close_chat_checkpointer()
        runtime_cm.exit.assert_awaited_once_with(None, None, None)

    asyncio.run(run_test())
