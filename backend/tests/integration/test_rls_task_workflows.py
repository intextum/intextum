"""Service-level RLS coverage for worker task processing workflows."""

from __future__ import annotations

import pytest

from rls import set_rls_context, worker_claim_context, worker_task_context
from services.task_queue import TaskQueueService
from tests.integration.rls_helpers import (
    admin_context,
    claim_process_document,
    create_process_task_state,
    enqueue_process_document,
    session_factory,
    set_psycopg_context,
)


pytestmark = pytest.mark.integration


def _assert_task_flow_completed(conn, content_item_id: str = "content-1") -> None:
    with conn.transaction():
        set_psycopg_context(
            conn,
            actor="user",
            user_sub="sub-admin",
            trustees='["everyone","sub:sub-admin","__acl_admin__"]',
            is_admin="true",
        )
        task_status = conn.execute(
            "SELECT status FROM task_queue WHERE content_item_id = %s",
            (content_item_id,),
        ).fetchone()
        audit_count = conn.execute(
            """
            SELECT count(*)
            FROM content_audit_events
            WHERE content_item_id = %s
              AND event_type = 'content.processing.completed'
            """,
            (content_item_id,),
        ).fetchone()
        outbox_count = conn.execute(
            """
            SELECT count(*)
            FROM event_outbox
            WHERE aggregate_id = %s
              AND event_type = 'user_event'
            """,
            (content_item_id,),
        ).fetchone()

    assert task_status == ("COMPLETED",)
    assert audit_count == (1,)
    assert outbox_count == (1,)


def _assert_task_flow_claimed(conn, content_item_id: str = "content-1") -> None:
    with conn.transaction():
        set_psycopg_context(
            conn,
            actor="user",
            user_sub="sub-admin",
            trustees='["everyone","sub:sub-admin","__acl_admin__"]',
            is_admin="true",
        )
        task_status = conn.execute(
            """
            SELECT status, claimed_by
            FROM task_queue
            WHERE content_item_id = %s
            """,
            (content_item_id,),
        ).fetchone()
        content_status = conn.execute(
            """
            SELECT processing_status, processed_by
            FROM indexed_content_items
            WHERE content_item_id = %s
            """,
            (content_item_id,),
        ).fetchone()
        audit_count = conn.execute(
            """
            SELECT count(*)
            FROM content_audit_events
            WHERE content_item_id = %s
              AND event_type = 'content.processing.started'
              AND actor_name = 'worker-1'
            """,
            (content_item_id,),
        ).fetchone()

    assert task_status == ("CLAIMED", "worker-1")
    assert content_status == ("PROCESSING", "worker-1")
    assert audit_count == (1,)


def _assert_service_process_completed_after_retry(conn) -> None:
    with conn.transaction():
        set_psycopg_context(
            conn,
            actor="user",
            user_sub="sub-admin",
            trustees='["everyone","sub:sub-admin","__acl_admin__"]',
            is_admin="true",
        )
        task_row = conn.execute(
            """
            SELECT status, claimed_by, retry_count, task_secret
            FROM task_queue
            WHERE content_item_id = 'service-content-1'
            """
        ).fetchone()
        content_row = conn.execute(
            """
            SELECT processing_status, processed_by, task_secret
            FROM indexed_content_items
            WHERE content_item_id = 'service-content-1'
            """
        ).fetchone()
        enrichment_row = conn.execute(
            """
            SELECT classification_status, classification_system_label,
                   extraction_status, extraction_system_schema_name
            FROM content_item_enrichment_states
            WHERE content_item_id = 'service-content-1'
            """
        ).fetchone()
        audit_events = conn.execute(
            """
            SELECT event_type
            FROM content_audit_events
            WHERE content_item_id = 'service-content-1'
            ORDER BY created_at, event_type
            """
        ).fetchall()
        outbox_count = conn.execute(
            """
            SELECT count(*)
            FROM event_outbox
            WHERE aggregate_id = 'service-content-1'
            """
        ).fetchone()

    assert task_row == ("COMPLETED", "worker-1", 1, None)
    assert content_row == ("COMPLETED", "worker-1", None)
    assert enrichment_row == ("completed", "Invoice", "skipped", None)
    assert [row[0] for row in audit_events] == [
        "content.created",
        "content.processing.queued",
        "content.processing.started",
        "content.processing.requeued",
        "content.processing.started",
        "content.processing.completed",
    ]
    assert outbox_count == (2,)


@pytest.mark.asyncio
async def test_worker_task_context_can_complete_task_service_flow(
    app_conn, rls_database
):
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
            ok = await TaskQueueService(session).complete_task(
                claimed.task_id,
                claimed.task_secret,
                worker_id="worker-1",
            )
            assert ok is True
    finally:
        await engine.dispose()

    _assert_task_flow_completed(app_conn)


@pytest.mark.asyncio
async def test_worker_claim_service_flow_switches_to_task_scope_for_audit(
    app_conn, rls_database
):
    await create_process_task_state(rls_database, state="PENDING")
    engine, factory = session_factory(database=rls_database)
    try:
        async with factory() as session:
            await set_rls_context(session, worker_claim_context("worker-1"))
            claimed = await TaskQueueService(session).claim_task(
                "worker-1",
                ["document"],
            )
            assert claimed is not None
            assert claimed.content_item_id == "content-1"
    finally:
        await engine.dispose()

    _assert_task_flow_claimed(app_conn)


@pytest.mark.asyncio
async def test_process_document_service_flow_can_retry_and_complete(
    app_conn, rls_database
):
    engine, factory = session_factory(database=rls_database)
    try:
        async with factory() as session:
            await set_rls_context(session, admin_context())
            await enqueue_process_document(session, content_item_id="service-content-1")

            first_claim = await claim_process_document(session)

            retry = await TaskQueueService(session).fail_task(
                first_claim.task_id,
                first_claim.task_secret,
                "temporary processor error",
                worker_id="worker-1",
            )
            assert retry is not None
            assert retry.requeued is True
            assert retry.new_task_secret

            second_claim = await claim_process_document(session)
            assert second_claim.task_id == first_claim.task_id
            assert second_claim.task_secret == retry.new_task_secret

            completed = await TaskQueueService(session).complete_task(
                second_claim.task_id,
                second_claim.task_secret,
                document_classification={
                    "status": "completed",
                    "label": "Invoice",
                    "confidence": 0.98,
                },
                document_extraction={
                    "status": "completed",
                    "schema_name": "invoice_fields",
                    "document_class": "Invoice",
                    "fields": {
                        "invoice_number": {
                            "value": "RE-42",
                            "evidence": [{"doc_refs": ["#/texts/1"]}],
                        },
                    },
                },
                worker_id="worker-1",
            )
            assert completed is True
    finally:
        await engine.dispose()

    _assert_service_process_completed_after_retry(app_conn)


@pytest.mark.asyncio
async def test_fatal_worker_failure_reaches_terminal_state(app_conn, rls_database):
    claimed = await create_process_task_state(
        rls_database,
        state="CLAIMED",
        content_item_id="fatal-content-1",
    )
    engine, factory = session_factory(database=rls_database)
    try:
        async with factory() as session:
            await set_rls_context(
                session,
                worker_task_context(
                    worker_id="worker-1",
                    task_id=claimed.task_id,
                    content_item_id="fatal-content-1",
                ),
            )
            result = await TaskQueueService(session).fail_task(
                claimed.task_id,
                claimed.task_secret,
                "FATAL: unsupported document",
                worker_id="worker-1",
            )
            assert result is not None
            assert result.requeued is False
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
        task_status = app_conn.execute(
            """
            SELECT status, task_secret
            FROM task_queue
            WHERE content_item_id = 'fatal-content-1'
            """
        ).fetchone()
        content_status = app_conn.execute(
            """
            SELECT processing_status, task_secret
            FROM indexed_content_items
            WHERE content_item_id = 'fatal-content-1'
            """
        ).fetchone()

    assert task_status == ("FAILED", None)
    assert content_status == ("FAILED", None)
