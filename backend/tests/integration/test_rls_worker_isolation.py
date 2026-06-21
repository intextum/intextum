"""RLS cross-worker isolation.

The ``task_queue`` and ``workers`` policies were tightened so a
``worker_claim`` actor can only see/modify rows belonging to itself (plus
PENDING tasks available to claim). These tests pin that boundary.
"""

from __future__ import annotations

import pytest
from sqlalchemy.future import select

from models.sqlalchemy_models import TaskQueue, Worker
from rls import set_rls_context, worker_claim_context
from services.task_queue import TaskQueueService
from tests.integration.rls_helpers import (
    admin_context,
    claim_process_document,
    enqueue_process_document,
    session_factory,
)


pytestmark = pytest.mark.integration


async def _register_workers(database: str, worker_ids: list[str]) -> None:
    engine, factory = session_factory(database=database)
    try:
        async with factory() as session:
            await set_rls_context(session, admin_context())
            for worker_id in worker_ids:
                session.add(
                    Worker(
                        id=worker_id,
                        name=worker_id,
                        description="integration worker",
                        config="{}",
                        status="active",
                    )
                )
            await session.commit()
    finally:
        await engine.dispose()


async def _enqueue_and_claim(
    database: str, *, content_item_id: str, relative_path: str, worker_id: str
) -> None:
    engine, factory = session_factory(database=database)
    try:
        async with factory() as session:
            await set_rls_context(session, admin_context())
            await enqueue_process_document(
                session,
                content_item_id=content_item_id,
                relative_path=relative_path,
            )
            await claim_process_document(session, worker_id=worker_id)
    finally:
        await engine.dispose()


async def _enqueue_pending(
    database: str, *, content_item_id: str, relative_path: str
) -> None:
    engine, factory = session_factory(database=database)
    try:
        async with factory() as session:
            await set_rls_context(session, admin_context())
            await enqueue_process_document(
                session,
                content_item_id=content_item_id,
                relative_path=relative_path,
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_worker_claim_cannot_see_other_workers_claimed_task(rls_database):
    """Worker A must not see (or update) a task claimed by worker B."""
    await _enqueue_and_claim(
        rls_database,
        content_item_id="content-1",
        relative_path="docs/one.pdf",
        worker_id="worker-1",
    )
    await _enqueue_and_claim(
        rls_database,
        content_item_id="content-2",
        relative_path="docs/two.pdf",
        worker_id="worker-2",
    )

    engine, factory = session_factory(database=rls_database)
    try:
        async with factory() as session:
            await set_rls_context(session, worker_claim_context("worker-1"))
            result = await session.execute(
                select(TaskQueue.content_item_id, TaskQueue.claimed_by)
                .where(TaskQueue.status == "CLAIMED")
                .order_by(TaskQueue.content_item_id)
            )
            visible = result.all()
            assert visible == [("content-1", "worker-1")], (
                f"worker-1 unexpectedly saw rows beyond its own claim: {visible}"
            )

            await set_rls_context(session, worker_claim_context("worker-2"))
            result = await session.execute(
                select(TaskQueue.content_item_id, TaskQueue.claimed_by)
                .where(TaskQueue.status == "CLAIMED")
                .order_by(TaskQueue.content_item_id)
            )
            visible_b = result.all()
            assert visible_b == [("content-2", "worker-2")]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_worker_claim_cannot_see_other_workers_row(rls_database):
    """The workers table must restrict each worker_claim to its own row."""
    await _register_workers(rls_database, ["worker-1", "worker-2"])

    engine, factory = session_factory(database=rls_database)
    try:
        async with factory() as session:
            await set_rls_context(session, worker_claim_context("worker-1"))
            result = await session.execute(select(Worker.id).order_by(Worker.id))
            assert result.scalars().all() == ["worker-1"]

            await set_rls_context(session, worker_claim_context("worker-2"))
            result = await session.execute(select(Worker.id).order_by(Worker.id))
            assert result.scalars().all() == ["worker-2"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_worker_claim_with_empty_id_can_browse_workers(rls_database):
    """During registration the worker_id is empty; that is the only time a
    worker_claim is allowed to see other rows in the workers table."""
    await _register_workers(rls_database, ["worker-1", "worker-2"])

    engine, factory = session_factory(database=rls_database)
    try:
        async with factory() as session:
            await set_rls_context(session, worker_claim_context())
            result = await session.execute(select(Worker.id).order_by(Worker.id))
            assert result.scalars().all() == ["worker-1", "worker-2"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_worker_claim_still_sees_pending_tasks_from_any_worker(rls_database):
    """worker_claim must see PENDING tasks regardless of who enqueued them
    (otherwise nobody could pick up work).
    """
    await _enqueue_and_claim(
        rls_database,
        content_item_id="content-1",
        relative_path="docs/one.pdf",
        worker_id="worker-1",
    )
    await _enqueue_pending(
        rls_database,
        content_item_id="content-2",
        relative_path="docs/two.pdf",
    )

    engine, factory = session_factory(database=rls_database)
    try:
        async with factory() as session:
            await set_rls_context(session, worker_claim_context("worker-2"))
            result = await session.execute(
                select(TaskQueue.content_item_id, TaskQueue.status).order_by(
                    TaskQueue.content_item_id
                )
            )
            visible = result.all()
            # worker-2 sees only the PENDING task — not worker-1's claimed task.
            assert visible == [("content-2", "PENDING")]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_worker_claim_cannot_claim_already_claimed_task(rls_database):
    """worker_claim cannot reach into another worker's CLAIMED task."""
    await _enqueue_and_claim(
        rls_database,
        content_item_id="content-1",
        relative_path="docs/one.pdf",
        worker_id="worker-1",
    )

    engine, factory = session_factory(database=rls_database)
    try:
        async with factory() as session:
            await set_rls_context(session, worker_claim_context("worker-2"))
            claimed = await TaskQueueService(session).claim_task(
                "worker-2", ["document"]
            )
            assert claimed is None
    finally:
        await engine.dispose()
