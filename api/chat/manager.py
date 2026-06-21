"""Shared LangGraph thread lifecycle helpers for chat streaming and CRUD."""

from collections.abc import AsyncIterator

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from chat.graph import build_request_scoped_chat_graph
from chat.snapshot import ChatThreadSnapshot
from chat.state import ChatThreadStatePatch
from chat.store import ChatThreadStore
from chat.transport import normalize_context_file_paths
from models.ai_settings import EffectiveAiSettings
from models.user import User


class ChatThreadManager:
    """Owns user-scoped LangGraph thread access for one request context."""

    def __init__(
        self,
        *,
        db: AsyncSession,
        user: User,
        context_file_paths: list[str] | None = None,
        ai_settings: EffectiveAiSettings | None = None,
        persist_checkpoints: bool = True,
    ):
        self.db = db
        self.user = user
        self.user_sub = user.require_stable_sub()
        self.context_file_paths = normalize_context_file_paths(context_file_paths or [])
        self.ai_settings = ai_settings
        self.persist_checkpoints = persist_checkpoints
        self._graph = None
        self._checkpoint_store = ChatThreadStore(db=db)
        self._graph_thread_store: ChatThreadStore | None = None

    def _build_graph(self):
        return build_request_scoped_chat_graph(
            db=self.db,
            user=self.user,
            context_file_paths=self.context_file_paths,
            ai_settings=self.ai_settings,
            persist_checkpoints=self.persist_checkpoints,
        )

    @property
    def graph(self):
        """Return a lazily compiled graph bound to the shared checkpointer."""
        if self._graph is None:
            self._graph = self._build_graph()
        return self._graph

    @property
    def checkpoint_store(self) -> ChatThreadStore:
        """Return a persistence adapter for checkpoint-only operations."""
        return self._checkpoint_store

    @property
    def graph_thread_store(self) -> ChatThreadStore:
        """Return a persistence adapter bound to the compiled conversation graph."""
        if self._graph_thread_store is None:
            self._graph_thread_store = ChatThreadStore(db=self.db, graph=self.graph)
        return self._graph_thread_store

    def owns_snapshot(self, snapshot: ChatThreadSnapshot | None) -> bool:
        """Return whether one thread state belongs to this manager's user."""
        return ChatThreadStore.is_thread_owned_by_user(snapshot, self.user_sub)

    def raise_if_not_owned(self, snapshot: ChatThreadSnapshot | None) -> None:
        """Raise a 404 when a thread exists but belongs to another user."""
        if snapshot is not None and not self.owns_snapshot(snapshot):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

    async def load_snapshot(self, thread_id: str) -> ChatThreadSnapshot | None:
        """Load the latest persisted snapshot for one thread."""
        return await self.graph_thread_store.load_snapshot(thread_id)

    async def load_accessible_snapshot(
        self, thread_id: str
    ) -> ChatThreadSnapshot | None:
        """Load one thread and raise when it belongs to another user."""
        snapshot = await self.load_snapshot(thread_id)
        self.raise_if_not_owned(snapshot)
        return snapshot

    async def load_owned_snapshot(self, thread_id: str) -> ChatThreadSnapshot | None:
        """Load one thread only when it belongs to this manager's user."""
        snapshot = await self.load_snapshot(thread_id)
        if not self.owns_snapshot(snapshot):
            return None
        return snapshot

    async def iter_owned_thread_snapshots(
        self, *, limit: int | None = None
    ) -> AsyncIterator[tuple[str, ChatThreadSnapshot]]:
        """Iterate newest-first thread state snapshots owned by this user."""
        seen_thread_ids: set[str] = set()

        async for checkpoint in self.checkpoint_store.list_checkpoints(limit=limit):
            thread_id = ChatThreadStore.checkpoint_thread_id(checkpoint)
            if not thread_id or thread_id in seen_thread_ids:
                continue

            seen_thread_ids.add(thread_id)
            snapshot = ChatThreadStore.checkpoint_snapshot(checkpoint)
            if snapshot is None or not self.owns_snapshot(snapshot):
                continue

            yield thread_id, snapshot

    async def update_state(
        self,
        thread_id: str,
        patch: ChatThreadStatePatch,
        *,
        as_node: str | None = None,
    ) -> None:
        """Persist a manual LangGraph state update for one thread."""
        await self.graph_thread_store.update_state(
            thread_id,
            patch,
            as_node=as_node,
        )

    async def delete_thread(self, thread_id: str) -> None:
        """Delete all persisted rows for one thread."""
        await self.checkpoint_store.delete_thread(thread_id)
