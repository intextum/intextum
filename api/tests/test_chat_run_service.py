"""Tests for durable chat run metadata service."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import and_, or_, select
from sqlalchemy.dialects import postgresql

from chat.run.service import ActiveChatRunExistsError, ChatRunService
from models.enums import ChatRunStatus
from models.sqlalchemy_models import ChatRun


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc).replace(tzinfo=None)


def _db_with_scalar_results(*values):
    db = AsyncMock()
    db.add = MagicMock()
    db.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=value)) for value in values
    ]
    return db


@pytest.mark.asyncio
async def test_create_run_persists_pending_record():
    db = _db_with_scalar_results(None)

    run = await ChatRunService(db).create_run(
        conversation_id="thread-1",
        user_sub="sub-testuser",
        request_payload={
            "conversation_id": "thread-1",
            "messages": [{"type": "human", "content": "Hello"}],
            "context_file_paths": ["documents/report.pdf"],
        },
    )

    assert run.conversation_id == "thread-1"
    assert run.user_sub == "sub-testuser"
    assert run.status == ChatRunStatus.PENDING.value
    assert run.id.startswith("run_")
    db.add.assert_called_once()
    added = db.add.call_args.args[0]
    assert isinstance(added, ChatRun)
    assert added.request_json["messages"][0]["content"] == "Hello"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_run_rejects_duplicate_active_runs():
    active_run = ChatRun(
        id="run_existing",
        conversation_id="thread-1",
        user_sub="sub-testuser",
        status=ChatRunStatus.RUNNING.value,
        request_json={},
        created_at=_utc(2026, 4, 23),
        updated_at=_utc(2026, 4, 23),
    )
    db = _db_with_scalar_results(active_run)

    with pytest.raises(ActiveChatRunExistsError):
        await ChatRunService(db).create_run(
            conversation_id="thread-1",
            user_sub="sub-testuser",
            request_payload={"conversation_id": "thread-1"},
        )

    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_owned_run_hides_missing_or_foreign_rows():
    db = _db_with_scalar_results(None)

    run = await ChatRunService(db).get_owned_run("run_missing", "sub-testuser")

    assert run is None


@pytest.mark.asyncio
async def test_claim_next_pending_run_marks_it_running():
    pending_run = ChatRun(
        id="run_pending",
        conversation_id="thread-1",
        user_sub="sub-testuser",
        status=ChatRunStatus.PENDING.value,
        request_json={"conversation_id": "thread-1"},
        created_at=_utc(2026, 4, 23, 9),
        updated_at=_utc(2026, 4, 23, 9),
    )
    db = _db_with_scalar_results(pending_run)

    claimed = await ChatRunService(db).claim_next_pending_run(
        claimed_by="backend-1",
        claim_timeout_seconds=300,
    )

    assert claimed is not None
    assert claimed.id == "run_pending"
    assert claimed.status == ChatRunStatus.RUNNING.value
    assert claimed.claimed_by == "backend-1"
    assert claimed.started_at is not None
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_claim_next_pending_run_reclaims_stale_running_run():
    stale_run = ChatRun(
        id="run_stale",
        conversation_id="thread-1",
        user_sub="sub-testuser",
        status=ChatRunStatus.RUNNING.value,
        request_json={"conversation_id": "thread-1"},
        claimed_by="backend-old",
        claimed_at=_utc(2026, 4, 23, 9),
        started_at=_utc(2026, 4, 23, 9),
        created_at=_utc(2026, 4, 23, 9),
        updated_at=_utc(2026, 4, 23, 9),
    )
    db = _db_with_scalar_results(stale_run)

    with patch("chat.run.service.utcnow", return_value=_utc(2026, 4, 23, 10)):
        claimed = await ChatRunService(db).claim_next_pending_run(
            claimed_by="backend-new",
            claim_timeout_seconds=300,
        )

    assert claimed is not None
    assert claimed.id == "run_stale"
    assert claimed.status == ChatRunStatus.RUNNING.value
    assert claimed.claimed_by == "backend-new"
    assert claimed.claimed_at == _utc(2026, 4, 23, 10)
    assert claimed.started_at == _utc(2026, 4, 23, 9)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_claim_next_pending_run_returns_none_when_no_run_is_claimable():
    db = _db_with_scalar_results(None)

    claimed = await ChatRunService(db).claim_next_pending_run(
        claimed_by="backend-1",
        claim_timeout_seconds=300,
    )

    assert claimed is None
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_claim_next_pending_run_reclaims_running_run_without_claim_timestamp():
    stale_run = ChatRun(
        id="run_missing_claim_time",
        conversation_id="thread-1",
        user_sub="sub-testuser",
        status=ChatRunStatus.RUNNING.value,
        request_json={"conversation_id": "thread-1"},
        claimed_by="backend-old",
        claimed_at=None,
        started_at=None,
        created_at=_utc(2026, 4, 23, 9),
        updated_at=_utc(2026, 4, 23, 9),
    )
    db = _db_with_scalar_results(stale_run)

    with patch("chat.run.service.utcnow", return_value=_utc(2026, 4, 23, 10)):
        claimed = await ChatRunService(db).claim_next_pending_run(
            claimed_by="backend-new",
            claim_timeout_seconds=300,
        )

    assert claimed is not None
    assert claimed.status == ChatRunStatus.RUNNING.value
    assert claimed.claimed_by == "backend-new"
    assert claimed.claimed_at == _utc(2026, 4, 23, 10)
    assert claimed.started_at == _utc(2026, 4, 23, 10)
    db.commit.assert_awaited_once()


def test_claim_next_pending_run_quotes_mode_column_for_postgres():
    stale_running_run = and_(
        ChatRun.status == ChatRunStatus.RUNNING.value,
        or_(
            ChatRun.claimed_at.is_(None),
            ChatRun.claimed_at < _utc(2026, 4, 23, 10),
        ),
    )
    query = (
        select(ChatRun)
        .where(
            or_(
                ChatRun.status == ChatRunStatus.PENDING.value,
                stale_running_run,
            )
        )
        .order_by(ChatRun.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )

    compiled = str(
        query.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert 'chat_runs."mode"' in compiled


@pytest.mark.asyncio
async def test_heartbeat_run_refreshes_owned_running_claim():
    running_run = ChatRun(
        id="run_running",
        conversation_id="thread-1",
        user_sub="sub-testuser",
        status=ChatRunStatus.RUNNING.value,
        request_json={"conversation_id": "thread-1"},
        claimed_by="backend-1",
        claimed_at=_utc(2026, 4, 23, 9),
        created_at=_utc(2026, 4, 23, 9),
        updated_at=_utc(2026, 4, 23, 9),
    )
    db = _db_with_scalar_results(running_run)

    with patch("chat.run.service.utcnow", return_value=_utc(2026, 4, 23, 10)):
        refreshed = await ChatRunService(db).heartbeat_run(
            "run_running",
            claimed_by="backend-1",
        )

    assert refreshed is True
    assert running_run.claimed_at == _utc(2026, 4, 23, 10)
    assert running_run.updated_at == _utc(2026, 4, 23, 10)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_heartbeat_run_returns_false_when_run_is_missing():
    db = _db_with_scalar_results(None)

    refreshed = await ChatRunService(db).heartbeat_run(
        "run_missing",
        claimed_by="backend-1",
    )

    assert refreshed is False
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "claimed_by"),
    [
        (ChatRunStatus.RUNNING.value, "backend-other"),
        (ChatRunStatus.COMPLETED.value, "backend-1"),
    ],
)
async def test_heartbeat_run_returns_false_when_claim_is_not_owned_or_active(
    status,
    claimed_by,
):
    run = ChatRun(
        id="run_running",
        conversation_id="thread-1",
        user_sub="sub-testuser",
        status=status,
        request_json={"conversation_id": "thread-1"},
        claimed_by=claimed_by,
        claimed_at=_utc(2026, 4, 23, 9),
        created_at=_utc(2026, 4, 23, 9),
        updated_at=_utc(2026, 4, 23, 9),
    )
    db = _db_with_scalar_results(run)

    refreshed = await ChatRunService(db).heartbeat_run(
        "run_running",
        claimed_by="backend-1",
    )

    assert refreshed is False
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_run_status_returns_status_enum():
    db = _db_with_scalar_results(ChatRunStatus.CANCELLED.value)

    status = await ChatRunService(db).get_run_status("run_cancelled")

    assert status == ChatRunStatus.CANCELLED


@pytest.mark.asyncio
async def test_get_run_status_returns_none_when_missing():
    db = _db_with_scalar_results(None)

    status = await ChatRunService(db).get_run_status("run_missing")

    assert status is None


@pytest.mark.asyncio
async def test_mark_completed_returns_none_when_missing():
    db = _db_with_scalar_results(None)

    completed = await ChatRunService(db).mark_completed(
        "run_missing",
        last_event_id="1713870000000-0",
    )

    assert completed is None
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_mark_failed_stores_terminal_metadata():
    running_run = ChatRun(
        id="run_running",
        conversation_id="thread-1",
        user_sub="sub-testuser",
        status=ChatRunStatus.RUNNING.value,
        request_json={"conversation_id": "thread-1"},
        created_at=_utc(2026, 4, 23, 9),
        updated_at=_utc(2026, 4, 23, 10),
    )
    db = _db_with_scalar_results(running_run)

    failed = await ChatRunService(db).mark_failed(
        "run_running",
        error_message="Chat generation failed.",
        last_event_id="1713870000000-0",
    )

    assert failed is not None
    assert failed.status == ChatRunStatus.FAILED.value
    assert failed.error_message == "Chat generation failed."
    assert failed.last_event_id == "1713870000000-0"
    assert failed.finished_at is not None
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_failed_returns_none_when_missing():
    db = _db_with_scalar_results(None)

    failed = await ChatRunService(db).mark_failed(
        "run_missing",
        error_message="Chat generation failed.",
    )

    assert failed is None
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_mark_cancelled_stores_terminal_event_metadata():
    running_run = ChatRun(
        id="run_running",
        conversation_id="thread-1",
        user_sub="sub-testuser",
        status=ChatRunStatus.RUNNING.value,
        request_json={"conversation_id": "thread-1"},
        created_at=_utc(2026, 4, 23, 9),
        updated_at=_utc(2026, 4, 23, 10),
    )
    db = _db_with_scalar_results(running_run)

    cancelled = await ChatRunService(db).mark_cancelled(
        "run_running",
        error_message="Cancelled by user.",
        last_event_id="1713870000003-0",
    )

    assert cancelled is not None
    assert cancelled.status == ChatRunStatus.CANCELLED.value
    assert cancelled.error_message == "Cancelled by user."
    assert cancelled.last_event_id == "1713870000003-0"
    assert cancelled.finished_at is not None
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_cancelled_returns_none_when_missing():
    db = _db_with_scalar_results(None)

    cancelled = await ChatRunService(db).mark_cancelled(
        "run_missing",
        error_message="Cancelled by user.",
    )

    assert cancelled is None
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_mark_cancelled_returns_existing_terminal_run_without_commit():
    completed_run = ChatRun(
        id="run_completed",
        conversation_id="thread-1",
        user_sub="sub-testuser",
        status=ChatRunStatus.COMPLETED.value,
        request_json={"conversation_id": "thread-1"},
        last_event_id="1713870000000-0",
        created_at=_utc(2026, 4, 23, 9),
        updated_at=_utc(2026, 4, 23, 10),
    )
    db = _db_with_scalar_results(completed_run)

    cancelled = await ChatRunService(db).mark_cancelled(
        "run_completed",
        error_message="Cancelled by user.",
        last_event_id="1713870000009-0",
    )

    assert cancelled is not None
    assert cancelled.status == ChatRunStatus.COMPLETED.value
    assert cancelled.last_event_id == "1713870000000-0"
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_touch_last_event_updates_replay_markers():
    running_run = ChatRun(
        id="run_running",
        conversation_id="thread-1",
        user_sub="sub-testuser",
        status=ChatRunStatus.RUNNING.value,
        request_json={"conversation_id": "thread-1"},
        created_at=_utc(2026, 4, 23, 9),
        updated_at=_utc(2026, 4, 23, 10),
    )
    db = _db_with_scalar_results(running_run)

    touched = await ChatRunService(db).touch_last_event(
        "run_running",
        event_id="1713870000002-0",
    )

    assert touched is not None
    assert touched.last_event_id == "1713870000002-0"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_touch_last_event_returns_none_when_missing():
    db = _db_with_scalar_results(None)

    touched = await ChatRunService(db).touch_last_event(
        "run_missing",
        event_id="1713870000002-0",
    )

    assert touched is None
    db.commit.assert_not_awaited()
