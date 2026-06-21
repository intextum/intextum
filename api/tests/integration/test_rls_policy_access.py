"""Focused Postgres RLS policy checks."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import ProgrammingError

from rls import set_rls_context, worker_task_context
from tests.integration.rls_helpers import (
    append_completed_audit,
    create_process_task_state,
    session_factory,
    set_psycopg_context,
    user_context,
)


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_without_rls_context_sees_no_protected_rows(app_conn, rls_database):
    await create_process_task_state(rls_database, state="PENDING")

    with app_conn.transaction():
        rows = app_conn.execute(
            "SELECT content_item_id FROM indexed_content_items"
        ).fetchall()

    assert rows == []


@pytest.mark.asyncio
async def test_worker_task_can_append_audit_after_task_completed(rls_database):
    claimed = await create_process_task_state(rls_database, state="COMPLETED")
    engine, factory = session_factory(database=rls_database)
    try:
        async with factory() as session:
            await set_rls_context(
                session,
                worker_task_context(
                    worker_id="worker-1",
                    task_id=claimed.task_id,
                    content_item_id="content-1",
                ),
            )
            await append_completed_audit(session)
            await session.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_worker_task_cannot_append_audit_for_other_content(rls_database):
    claimed = await create_process_task_state(rls_database, state="COMPLETED")
    engine, factory = session_factory(database=rls_database)
    try:
        with pytest.raises(ProgrammingError):
            async with factory() as session:
                await set_rls_context(
                    session,
                    worker_task_context(
                        worker_id="worker-1",
                        task_id=claimed.task_id,
                        content_item_id="content-1",
                    ),
                )
                await append_completed_audit(session, content_item_id="other-content")
                await session.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_user_can_append_own_fallback_audit_without_content_row(rls_database):
    engine, factory = session_factory(database=rls_database)
    try:
        async with factory() as session:
            await set_rls_context(session, user_context(user_sub="sub-alice"))
            await append_completed_audit(
                session,
                content_item_id="missing-content",
                actor_sub="sub-alice",
            )
            await session.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_user_cannot_append_fallback_audit_for_other_actor(rls_database):
    engine, factory = session_factory(database=rls_database)
    try:
        with pytest.raises(ProgrammingError):
            async with factory() as session:
                await set_rls_context(session, user_context(user_sub="sub-alice"))
                await append_completed_audit(
                    session,
                    content_item_id="missing-content",
                    actor_sub="sub-bob",
                )
                await session.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_normal_user_reads_allowed_content(app_conn, rls_database):
    await create_process_task_state(rls_database, state="PENDING")

    with app_conn.transaction():
        set_psycopg_context(
            app_conn,
            actor="user",
            user_sub="sub-reader",
            trustees='["everyone","sub:sub-reader"]',
        )
        rows = app_conn.execute(
            "SELECT content_item_id FROM indexed_content_items"
        ).fetchall()

    assert rows == [("content-1",)]
