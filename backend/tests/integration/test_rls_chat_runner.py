"""RLS coverage for the chat_runner actor.

The chat runner switches its session to ``chat_runner_context(user)`` after
claiming a run so that retrieval and conversation reads run with the run
owner's trustees. These tests pin that behaviour:

* A chat run executing on behalf of alice sees alice's content but not bob's.
* A bare ``internal_context("chat_runner")`` (no user_sub) sees no user
  content at all — the actor alone must not grant access.
"""

from __future__ import annotations

import pytest
from sqlalchemy.future import select

from models.sqlalchemy_models import IndexedContentItem
from models.user import User
from rls import chat_runner_context, internal_context, set_rls_context
from services.vector import VectorService
from tests.integration.rls_helpers import (
    admin_context,
    create_indexed_document_with_chunk,
    session_factory,
)


pytestmark = pytest.mark.integration


async def _seed_two_user_docs(database: str) -> None:
    engine, factory = session_factory(database=database)
    try:
        async with factory() as session:
            await set_rls_context(session, admin_context())
            await create_indexed_document_with_chunk(
                session,
                content_item_id="alice-doc",
                allowed_viewers=["sub:sub-alice"],
            )
            await create_indexed_document_with_chunk(
                session,
                content_item_id="bob-doc",
                allowed_viewers=["sub:sub-bob"],
            )
    finally:
        await engine.dispose()


def _alice() -> User:
    return User(username="alice", sub="sub-alice", groups=[])


def _bob() -> User:
    return User(username="bob", sub="sub-bob", groups=[])


@pytest.mark.asyncio
async def test_chat_runner_context_admits_only_run_owner_content(rls_database):
    """Vector retrieval inside a chat run only sees the owner's content."""
    await _seed_two_user_docs(rls_database)

    engine, factory = session_factory(database=rls_database)
    try:
        async with factory() as session:
            await set_rls_context(session, chat_runner_context(_alice()))
            alice_chunks = await VectorService.fetch_document_chunks(
                session, "alice-doc"
            )
            assert [c.content_item_id for c in alice_chunks] == ["alice-doc"]

            bob_chunks_for_alice = await VectorService.fetch_document_chunks(
                session, "bob-doc"
            )
            assert bob_chunks_for_alice == []

            await set_rls_context(session, chat_runner_context(_bob()))
            bob_chunks = await VectorService.fetch_document_chunks(session, "bob-doc")
            assert [c.content_item_id for c in bob_chunks] == ["bob-doc"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_chat_runner_without_user_identity_sees_no_content(rls_database):
    """A bare chat_runner actor must not grant content access on its own."""
    await _seed_two_user_docs(rls_database)

    engine, factory = session_factory(database=rls_database)
    try:
        async with factory() as session:
            await set_rls_context(session, internal_context("chat_runner"))
            result = await session.execute(select(IndexedContentItem.content_item_id))
            assert result.scalars().all() == []
    finally:
        await engine.dispose()
