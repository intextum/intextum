"""LangGraph thread persistence helpers."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from chat.checkpointer import get_chat_checkpointer
from chat.snapshot import ChatThreadSnapshot
from chat.state import ChatThreadStatePatch


def thread_config(thread_id: str) -> dict[str, dict[str, str]]:
    """Build the LangGraph config object for one thread."""
    return {"configurable": {"thread_id": thread_id}}


class ChatThreadStore:
    """Small adapter around LangGraph persistence and checkpoint storage."""

    def __init__(self, *, db: AsyncSession, graph: Any | None = None):
        self.db = db
        self.graph = graph

    def _require_graph(self) -> Any:
        if self.graph is None:
            raise RuntimeError("ChatThreadStore requires a graph for this operation")
        return self.graph

    @staticmethod
    def _field(container: Any, key: str) -> Any:
        """Read one field from either a mapping or an attribute-bearing object."""
        if isinstance(container, dict):
            return container.get(key)
        return getattr(container, key, None)

    @staticmethod
    def checkpoint_snapshot(checkpoint: Any) -> ChatThreadSnapshot | None:
        """Extract a typed thread snapshot from one LangGraph checkpoint tuple."""
        checkpoint_data = ChatThreadStore._field(checkpoint, "checkpoint")
        if not isinstance(checkpoint_data, dict):
            return None

        values = checkpoint_data.get("channel_values")
        if not isinstance(values, dict):
            return None
        return ChatThreadSnapshot.from_state_values(values)

    @staticmethod
    def checkpoint_thread_id(checkpoint: Any) -> str | None:
        """Extract the thread id from a LangGraph checkpoint tuple."""
        config = ChatThreadStore._field(checkpoint, "config")
        if not isinstance(config, dict):
            return None

        configurable = config.get("configurable")
        if not isinstance(configurable, dict):
            return None

        thread_id = configurable.get("thread_id")
        return thread_id if isinstance(thread_id, str) else None

    @staticmethod
    def is_thread_owned_by_user(
        snapshot: ChatThreadSnapshot | None, user_sub: str
    ) -> bool:
        """Return whether a thread state belongs to the authenticated user."""
        if snapshot is None:
            return False

        return snapshot.user_sub == user_sub

    async def load_snapshot(self, thread_id: str) -> ChatThreadSnapshot | None:
        """Load the latest typed snapshot for a LangGraph thread."""
        config = thread_config(thread_id)
        checkpoint = await get_chat_checkpointer().aget_tuple(config)
        if checkpoint is None:
            return None

        snapshot = await self._require_graph().aget_state(config)
        return ChatThreadSnapshot.from_state_values(snapshot.values)

    async def list_checkpoints(self, *, limit: int | None = None) -> AsyncIterator[Any]:
        """Iterate persisted checkpoints in newest-first order."""
        async for checkpoint in get_chat_checkpointer().alist(None, limit=limit):
            yield checkpoint

    async def update_state(
        self,
        thread_id: str,
        patch: ChatThreadStatePatch,
        *,
        as_node: str | None = None,
    ) -> None:
        """Persist a manual LangGraph state update for one thread."""
        await self._require_graph().aupdate_state(
            thread_config(thread_id),
            patch.to_state_update(),
            as_node=as_node,
        )

    @staticmethod
    @asynccontextmanager
    async def _checkpointer_cursor(checkpointer: Any):
        """Yield a raw async cursor for saver implementations without delete support."""
        if not hasattr(checkpointer, "_cursor"):
            raise RuntimeError("Chat checkpointer does not support raw cursor deletion")

        async with checkpointer._cursor(pipeline=True) as cur:  # type: ignore[attr-defined]
            yield cur

    async def _delete_thread_via_sql(self, thread_id: str) -> None:
        """Delete one thread from the shallow checkpoint tables directly."""
        checkpointer = get_chat_checkpointer()
        async with self._checkpointer_cursor(checkpointer) as cur:
            await cur.execute(
                "DELETE FROM checkpoint_writes WHERE thread_id = %s",
                (thread_id,),
            )
            await cur.execute(
                "DELETE FROM checkpoint_blobs WHERE thread_id = %s",
                (thread_id,),
            )
            await cur.execute(
                "DELETE FROM checkpoints WHERE thread_id = %s",
                (thread_id,),
            )

    async def delete_thread(self, thread_id: str) -> None:
        """Delete persisted rows for one thread via the checkpointer API or SQL fallback."""
        checkpointer = get_chat_checkpointer()
        try:
            await checkpointer.adelete_thread(thread_id)
        except NotImplementedError:
            await self._delete_thread_via_sql(thread_id)
