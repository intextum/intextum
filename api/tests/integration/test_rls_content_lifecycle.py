"""Service-level RLS coverage for content ownership and deletion."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import ProgrammingError

from rls import set_rls_context
from services.content.deletion import ContentDeletionService
from services.vector import VectorService
from tests.integration.rls_helpers import (
    admin_context,
    create_indexed_document_with_chunk,
    enqueue_process_document,
    session_factory,
    set_psycopg_context,
    user_context,
    visible_content_ids,
)


pytestmark = pytest.mark.integration


async def _create_acl_content(database: str) -> None:
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
                content_item_id="group-doc",
                allowed_viewers=["group:reviewers"],
            )
            await create_indexed_document_with_chunk(
                session,
                content_item_id="denied-doc",
                allowed_viewers=["everyone"],
                denied_viewers=["sub:sub-bob"],
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_content_acl_ownership_filters_items_and_child_chunks(
    app_conn,
    rls_database,
):
    await _create_acl_content(rls_database)

    assert visible_content_ids(
        app_conn,
        user_sub="sub-alice",
        trustees='["everyone","sub:sub-alice"]',
    ) == ["alice-doc", "denied-doc"]
    assert visible_content_ids(
        app_conn,
        user_sub="sub-reviewer",
        trustees='["everyone","sub:sub-reviewer","group:reviewers"]',
    ) == ["denied-doc", "group-doc"]
    assert (
        visible_content_ids(
            app_conn,
            user_sub="sub-bob",
            trustees='["everyone","sub:sub-bob"]',
        )
        == []
    )

    engine, factory = session_factory(database=rls_database)
    try:
        async with factory() as session:
            await set_rls_context(session, user_context(user_sub="sub-alice"))
            chunks = await VectorService.fetch_document_chunks(session, "alice-doc")
            assert [chunk.content_item_id for chunk in chunks] == ["alice-doc"]

            await set_rls_context(session, user_context(user_sub="sub-bob"))
            chunks = await VectorService.fetch_document_chunks(session, "alice-doc")
            assert chunks == []
            search_hits = await VectorService.semantic_search(
                session,
                query_vector=[0.01] * 1024,
                limit=10,
            )
            assert search_hits == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_visible_content_deletion_removes_content_chunks_tasks_and_audit(
    app_conn,
    rls_database,
):
    engine, factory = session_factory(database=rls_database)
    try:
        async with factory() as session:
            await set_rls_context(session, admin_context())
            await create_indexed_document_with_chunk(
                session,
                content_item_id="delete-doc",
                relative_path="docs/delete-doc.pdf",
                allowed_viewers=["sub:sub-alice"],
            )
            await enqueue_process_document(
                session,
                content_item_id="delete-doc",
                relative_path="docs/delete-doc.pdf",
                requested_by_sub="sub-alice",
            )

            result = await ContentDeletionService(session).delete_content_path(
                folder_uuid="folder-1",
                relative_path="docs/delete-doc.pdf",
                content_item_id="delete-doc",
                actor_sub="sub-admin",
                source="integration",
            )

            assert result.deleted_record_count == 1
            assert result.deleted_task_count == 1
            assert result.cleaned_content_item_ids == ("delete-doc",)
    finally:
        await engine.dispose()

    with app_conn.transaction():
        set_psycopg_context(
            app_conn,
            actor="user",
            user_sub="sub-admin",
            trustees='["everyone","sub:sub-admin","__acl_admin__"]',
            is_admin="true",
        )
        content_count = app_conn.execute(
            "SELECT count(*) FROM indexed_content_items WHERE content_item_id = 'delete-doc'"
        ).fetchone()
        chunk_count = app_conn.execute(
            "SELECT count(*) FROM content_chunks WHERE content_item_id = 'delete-doc'"
        ).fetchone()
        task_count = app_conn.execute(
            "SELECT count(*) FROM task_queue WHERE content_item_id = 'delete-doc'"
        ).fetchone()
        audit_count = app_conn.execute(
            """
            SELECT count(*)
            FROM content_audit_events
            WHERE content_item_id = 'delete-doc'
              AND event_type = 'content.deleted'
            """
        ).fetchone()

    assert content_count == (0,)
    assert chunk_count == (0,)
    assert task_count == (0,)
    assert audit_count == (1,)


@pytest.mark.asyncio
async def test_inaccessible_content_deletion_fails_without_deleting_or_auditing(
    app_conn,
    rls_database,
):
    engine, factory = session_factory(database=rls_database)
    try:
        async with factory() as session:
            await set_rls_context(session, admin_context())
            await create_indexed_document_with_chunk(
                session,
                content_item_id="private-doc",
                relative_path="docs/private-doc.pdf",
                allowed_viewers=["sub:sub-alice"],
            )

        with pytest.raises(ProgrammingError):
            async with factory() as session:
                await set_rls_context(session, user_context(user_sub="sub-bob"))
                await ContentDeletionService(session).delete_content_path(
                    folder_uuid="folder-1",
                    relative_path="docs/private-doc.pdf",
                    content_item_id="private-doc",
                    actor_sub="sub-bob",
                    source="integration",
                )
    finally:
        await engine.dispose()

    with app_conn.transaction():
        set_psycopg_context(
            app_conn,
            actor="user",
            user_sub="sub-admin",
            trustees='["everyone","sub:sub-admin","__acl_admin__"]',
            is_admin="true",
        )
        content_count = app_conn.execute(
            "SELECT count(*) FROM indexed_content_items WHERE content_item_id = 'private-doc'"
        ).fetchone()
        audit_count = app_conn.execute(
            """
            SELECT count(*)
            FROM content_audit_events
            WHERE content_item_id = 'private-doc'
              AND event_type = 'content.deleted'
            """
        ).fetchone()

    assert content_count == (1,)
    assert audit_count == (0,)
