"""Shared LangGraph checkpointer lifecycle for chat threads."""

from contextlib import AbstractAsyncContextManager
from typing import Any, cast

from database import CHECKPOINTER_DATABASE_URL, CHECKPOINTER_SETUP_DATABASE_URL
from langgraph.checkpoint.postgres.aio import AsyncShallowPostgresSaver

_checkpointer_cm: AbstractAsyncContextManager[Any] | None = None
_checkpointer: AsyncShallowPostgresSaver | None = None


async def init_chat_checkpointer() -> None:
    """Initialize the shared chat checkpointer once at startup."""
    global _checkpointer_cm, _checkpointer

    if _checkpointer is not None:
        return

    setup_cm = AsyncShallowPostgresSaver.from_conn_string(
        CHECKPOINTER_SETUP_DATABASE_URL
    )
    setup_checkpointer = cast(AsyncShallowPostgresSaver, await setup_cm.__aenter__())
    try:
        await setup_checkpointer.setup()
    finally:
        await setup_cm.__aexit__(None, None, None)

    cm = AsyncShallowPostgresSaver.from_conn_string(CHECKPOINTER_DATABASE_URL)
    checkpointer = cast(AsyncShallowPostgresSaver, await cm.__aenter__())

    _checkpointer_cm = cast(AbstractAsyncContextManager[Any], cm)
    _checkpointer = checkpointer


async def close_chat_checkpointer() -> None:
    """Close the shared chat checkpointer on shutdown."""
    global _checkpointer_cm, _checkpointer

    if _checkpointer_cm is not None:
        await _checkpointer_cm.__aexit__(None, None, None)

    _checkpointer_cm = None
    _checkpointer = None


def get_chat_checkpointer() -> AsyncShallowPostgresSaver:
    """Return the initialized chat checkpointer."""
    if _checkpointer is None:
        raise RuntimeError("Chat checkpointer has not been initialized")
    return _checkpointer
