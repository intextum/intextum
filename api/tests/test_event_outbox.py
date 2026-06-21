"""Tests for durable event outbox dispatch."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app_runtime import event_outbox_dispatch_loop
from models.sqlalchemy_models import EventOutbox
from services.event_outbox import EventOutboxService


def _db_with_rows(rows):
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    db.execute.return_value = result
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_dispatch_pending_retries_user_event_when_publish_backend_is_unavailable():
    row = EventOutbox(
        id="outbox-1",
        event_type="user_event",
        aggregate_type="file",
        aggregate_id="file-1",
        user_sub="sub-user",
        payload_json={
            "kind": "file.process.completed",
            "resource_type": "file",
            "resource_id": "file-1",
            "status": "COMPLETED",
            "metadata": {},
            "created_at": "2026-05-04T10:00:00Z",
        },
        status="pending",
    )
    db = _db_with_rows([row])

    with (
        patch("services.event_outbox.is_valkey_configured", return_value=True),
        patch(
            "services.event_outbox.init_valkey_client", new=AsyncMock(return_value=None)
        ),
    ):
        processed = await EventOutboxService(db).dispatch_pending()

    assert processed == 0
    assert row.status == "pending"
    assert row.attempts == 1
    assert row.last_error
    assert row.next_attempt_at is not None
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_pending_marks_user_event_processed_after_success():
    row = EventOutbox(
        id="outbox-1",
        event_type="user_event",
        aggregate_type="file",
        aggregate_id="file-1",
        user_sub="sub-user",
        payload_json={
            "kind": "file.process.completed",
            "resource_type": "file",
            "resource_id": "file-1",
            "status": "COMPLETED",
            "metadata": {},
            "created_at": "2026-05-04T10:00:00Z",
        },
        status="pending",
    )
    db = _db_with_rows([row])

    with (
        patch("services.event_outbox.is_valkey_configured", return_value=True),
        patch(
            "services.event_outbox.init_valkey_client",
            new=AsyncMock(return_value=object()),
        ),
        patch(
            "services.event_outbox.UserEventStore.append_event",
            new=AsyncMock(),
        ) as append_event,
    ):
        processed = await EventOutboxService(db).dispatch_pending()

    assert processed == 1
    assert row.status == "processed"
    assert row.processed_at is not None
    append_event.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_event_outbox_dispatch_loop_sleeps_when_no_rows():
    class SessionFactory:
        async def __aenter__(self):
            return AsyncMock()

        async def __aexit__(self, exc_type, exc, traceback):
            return None

    def session_factory():
        return SessionFactory()

    sleep = AsyncMock(side_effect=asyncio.CancelledError)
    dispatch_pending = AsyncMock(return_value=0)

    with (
        patch("app_runtime.asyncio.sleep", sleep),
        patch(
            "services.event_outbox.EventOutboxService.dispatch_pending",
            dispatch_pending,
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        await event_outbox_dispatch_loop(
            session_factory=session_factory,
            logger=MagicMock(),
            poll_interval_seconds=0.25,
        )

    dispatch_pending.assert_awaited_once()
    sleep.assert_awaited_once_with(0.25)
