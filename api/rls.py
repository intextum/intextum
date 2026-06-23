"""Postgres row-level-security request context.

The DDL that defines RLS policies, helper functions, and the runtime role
lives in ``backend/sql/rls/*.sql`` and is applied by the Alembic migration.
This module only provides the Python side: a frozen ``RlsContext`` dataclass,
constructor helpers per actor, and ``set_rls_context`` which serializes the
context into transaction-local ``app.*`` GUCs the SQL policies read.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import AsyncIterator
from typing import Literal

from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from models.user import User
from trustees import build_user_trustees

RlsActor = Literal[
    "anonymous",
    "user",
    "auth",
    "worker_claim",
    "worker_task",
    "watcher",
    "stale_cleanup",
    "event_outbox",
    "chat_runner",
]

_RLS_CONTEXT_KEY = "rls_context"

_SET_CONTEXT_SQL = text(
    """
    SELECT
        set_config('app.actor', :actor, true),
        set_config('app.user_sub', :user_sub, true),
        set_config('app.trustees', :trustees, true),
        set_config('app.is_admin', :is_admin, true),
        set_config('app.worker_id', :worker_id, true),
        set_config('app.task_id', :task_id, true),
        set_config('app.content_item_id', :content_item_id, true)
    """
)


@dataclass(frozen=True)
class RlsContext:
    """Transaction-local Postgres actor context."""

    actor: RlsActor
    user_sub: str = ""
    trustees: list[str] = field(default_factory=list)
    is_admin: bool = False
    worker_id: str = ""
    task_id: str = ""
    content_item_id: str = ""

    def params(self) -> dict[str, str]:
        """Return bind-safe values for the SET LOCAL statement."""
        return {
            "actor": self.actor,
            "user_sub": self.user_sub,
            "trustees": json.dumps(self.trustees),
            "is_admin": "true" if self.is_admin else "false",
            "worker_id": self.worker_id,
            "task_id": self.task_id,
            "content_item_id": self.content_item_id,
        }


def anonymous_context() -> RlsContext:
    """Return the fail-closed unauthenticated request context."""
    return RlsContext(actor="anonymous", trustees=["everyone"])


def user_context(user: User | None) -> RlsContext:
    """Build an RLS context from the request user."""
    if user is None:
        return anonymous_context()
    return RlsContext(
        actor="user",
        user_sub=user.normalized_sub or "",
        trustees=build_user_trustees(user),
        is_admin=user.is_admin,
    )


def internal_context(actor: RlsActor) -> RlsContext:
    """Build a narrow internal actor context."""
    if actor in {"anonymous", "user", "worker_task"}:
        raise ValueError(f"{actor} is not an internal context")
    return RlsContext(actor=actor)


def worker_claim_context(worker_id: str = "") -> RlsContext:
    """Build context for worker-token and task-claim operations."""
    return RlsContext(actor="worker_claim", worker_id=worker_id)


def worker_task_context(
    *, worker_id: str, task_id: str, content_item_id: str
) -> RlsContext:
    """Build context for one active worker task."""
    return RlsContext(
        actor="worker_task",
        worker_id=worker_id,
        task_id=task_id,
        content_item_id=content_item_id,
    )


def chat_runner_context(user: User) -> RlsContext:
    """Context for a chat run executing on behalf of a specific user.

    The actor stays ``chat_runner`` so policies that gate by actor name
    (app_settings, document_classes, extraction_schemas, …) still grant
    access, but the run owner's identity is populated so ACL- and
    ``user_sub_own``-based policies (conversations, content items, research
    reports) naturally admit that user's own rows.
    """
    return RlsContext(
        actor="chat_runner",
        user_sub=user.normalized_sub or "",
        trustees=build_user_trustees(user),
        is_admin=user.is_admin,
    )


def _apply_context(connection: Connection, context: RlsContext) -> None:
    connection.execute(_SET_CONTEXT_SQL, context.params())


def _session_context(session: Session) -> RlsContext | None:
    context = session.info.get(_RLS_CONTEXT_KEY)
    return context if isinstance(context, RlsContext) else None


@event.listens_for(Session, "after_begin")
def _apply_context_after_begin(
    session: Session, _transaction, connection: Connection
) -> None:
    context = _session_context(session)
    if context is not None:
        _apply_context(connection, context)


async def set_rls_context(db: AsyncSession, context: RlsContext) -> None:
    """Store and apply the RLS context for this session.

    The SQLAlchemy event listener reapplies the same context whenever a new
    transaction begins, so ``SET LOCAL`` remains safe with pooled connections
    even when service methods commit mid-request.
    """
    db.sync_session.info[_RLS_CONTEXT_KEY] = context
    await db.execute(_SET_CONTEXT_SQL, context.params())


@asynccontextmanager
async def rls_session(
    session_factory: Callable[[], AsyncSession],
    context: RlsContext,
) -> AsyncIterator[AsyncSession]:
    """Open a session and apply an RLS context before yielding it."""
    async with session_factory() as db:
        await set_rls_context(db, context)
        yield db


def rls_session_factory(
    session_factory: Callable[[], AsyncSession],
    context: RlsContext,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Return a session factory that applies one RLS context to every session."""

    @asynccontextmanager
    async def _factory() -> AsyncIterator[AsyncSession]:
        async with rls_session(session_factory, context) as db:
            yield db

    return _factory
