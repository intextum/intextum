"""Pin the worker_task access boundary across the task lifecycle.

``app.can_worker_task_access`` requires the matching task_queue row to be in
``CLAIMED`` state. This is what makes worker_task ACL access self-revoking
once a task is completed, failed, or aborted. These tests fence the boundary
on both sides:

* While a task is CLAIMED, a worker_task can read/write the linked content.
* The moment the task transitions to a terminal state, that access is gone
  — even if the same RlsContext is replayed afterwards.

The audit-event policy intentionally relaxes this constraint (it checks only
``content_item_id = current_content_item_id()``), so workers can post a final
``content.processing.completed`` audit row. That separate path is covered by
``test_rls_policy_access.py``.

A subtler concern is "what about writes that complete_task itself performs
*after* setting status=COMPLETED in the ORM?". In practice the session uses
autoflush=False and a single commit at the end, so the UPDATE on task_queue
is not flushed to the DB until every dependent write has been issued.
``can_worker_task_access`` therefore still sees ``status='CLAIMED'`` for the
duration of the request. ``test_process_document_service_flow_can_retry_and_complete``
in ``test_rls_task_workflows.py`` exercises that end-to-end.
"""

from __future__ import annotations

import pytest
from sqlalchemy import update

from models.sqlalchemy_models import IndexedContentItem
from rls import set_rls_context, worker_task_context
from tests.integration.rls_helpers import (
    create_process_task_state,
    session_factory,
    set_psycopg_context,
)


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_worker_task_can_update_indexed_content_while_claimed(rls_database):
    """While the task is CLAIMED, worker_task may update the linked content."""
    claimed = await create_process_task_state(rls_database, state="CLAIMED")

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
            await session.execute(
                update(IndexedContentItem)
                .where(IndexedContentItem.content_item_id == "content-1")
                .values(processing_status="PROCESSING")
            )
            await session.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_worker_task_cannot_update_indexed_content_after_completion(
    rls_database, app_conn
):
    """Once the task is COMPLETED, replaying worker_task context no longer
    grants write access to indexed_content_items.

    The UPDATE silently affects 0 rows (RLS hides the row from the worker)
    rather than raising — which is RLS's normal failure mode for ``USING``
    predicates. We assert the post-state via the admin role instead.
    """
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
            await session.execute(
                update(IndexedContentItem)
                .where(IndexedContentItem.content_item_id == "content-1")
                .values(error_message="worker should not be able to write this")
            )
            await session.commit()
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
        row = app_conn.execute(
            "SELECT error_message FROM indexed_content_items "
            "WHERE content_item_id = %s",
            ("content-1",),
        ).fetchone()

    assert row == (None,), (
        f"worker_task unexpectedly wrote to indexed_content_items "
        f"after task completion: {row}"
    )
