"""Tests for resumable conversation run endpoints."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth.dependencies import require_user
from chat.run.service import ActiveChatRunExistsError
from database import get_db
from models.chat.runs import ChatRunEvent, ChatRunRecord
from models.enums import ChatRunStatus
from models.user import User
from routers.conversations import router as conversations_router


@pytest.fixture
def conversation_runs_client():
    """FastAPI test client with the full conversations package router."""
    app = FastAPI()
    app.include_router(conversations_router, prefix="/api/conversations")

    user = User(username="testuser", sub="sub-testuser", is_admin=True)
    mock_db = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

    app.dependency_overrides.clear()


def _run_record(status: ChatRunStatus) -> ChatRunRecord:
    return ChatRunRecord.model_validate(
        {
            "id": "run_123",
            "conversation_id": "thread-1",
            "user_sub": "sub-testuser",
            "status": status.value,
            "created_at": "2026-04-23T10:00:00",
            "updated_at": "2026-04-23T10:00:00",
        }
    )


def _event(
    event: str,
    event_id: str,
    payload: dict | None = None,
) -> ChatRunEvent:
    return ChatRunEvent(
        event=event,
        payload={} if payload is None else payload,
        run_id="run_123",
        conversation_id="thread-1",
        event_id=event_id,
    )


def test_create_conversation_run_returns_run_metadata(conversation_runs_client):
    with (
        patch("routers.conversations.runs._runs_enabled", return_value=True),
        patch(
            "routers.conversations.runs.ConversationService.ensure_conversation_for_submission",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "routers.conversations.runs.ChatRunService.create_run",
            new=AsyncMock(return_value=_run_record(ChatRunStatus.PENDING)),
        ) as create_run,
    ):
        response = conversation_runs_client.post(
            "/api/conversations/runs",
            json={
                "input": {
                    "messages": [
                        {"id": "msg-1", "type": "human", "content": "Hello world"}
                    ],
                    "context_file_paths": ["docs/report.pdf"],
                },
                "config": {"configurable": {"thread_id": "thread-1"}},
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "run_id": "run_123",
        "conversation_id": "thread-1",
        "mode": "chat",
        "research_report_id": None,
        "status": "PENDING",
    }
    create_run.assert_awaited_once()
    payload = create_run.await_args.kwargs["request_payload"]
    assert payload["conversation_id"] == "thread-1"
    assert payload["user"]["sub"] == "sub-testuser"
    assert payload["user"]["is_admin"] is True
    assert payload["messages"][0]["content"] == "Hello world"


def test_create_conversation_run_creates_research_mode_run(conversation_runs_client):
    report = SimpleNamespace(id="report_123")

    with (
        patch("routers.conversations.runs._runs_enabled", return_value=True),
        patch(
            "routers.conversations.runs.ConversationService.ensure_conversation_for_submission",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "routers.conversations.runs.ConversationService.persist_submitted_messages",
            new=AsyncMock(return_value=None),
        ) as persist_submission,
        patch(
            "routers.conversations.runs.ResearchReportService.create_report",
            new=AsyncMock(return_value=report),
        ) as create_report,
        patch(
            "routers.conversations.runs.ChatRunService.create_run",
            new=AsyncMock(
                return_value=ChatRunRecord.model_validate(
                    {
                        "id": "run_research_123",
                        "conversation_id": "thread-1",
                        "user_sub": "sub-testuser",
                        "mode": "research",
                        "research_report_id": "report_123",
                        "status": "PENDING",
                        "created_at": "2026-04-24T10:00:00",
                        "updated_at": "2026-04-24T10:00:00",
                    }
                )
            ),
        ) as create_run,
    ):
        response = conversation_runs_client.post(
            "/api/conversations/runs",
            json={
                "input": {
                    "mode": "research",
                    "messages": [
                        {
                            "id": "msg-1",
                            "type": "human",
                            "content": "Create a grounded retention report.",
                        }
                    ],
                    "context_file_paths": ["docs/report.pdf"],
                },
                "config": {"configurable": {"thread_id": "thread-1"}},
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "run_id": "run_research_123",
        "conversation_id": "thread-1",
        "mode": "research",
        "research_report_id": "report_123",
        "status": "PENDING",
    }
    create_report.assert_awaited_once_with(
        conversation_id="thread-1",
        user_sub="sub-testuser",
        prompt="Create a grounded retention report.",
        context_file_paths=["docs/report.pdf"],
        title="Create a grounded retention report.",
    )
    create_run.assert_awaited_once()
    payload = create_run.await_args.kwargs["request_payload"]
    assert payload["mode"] == "research"
    assert payload["research_report_id"] == "report_123"
    persist_submission.assert_awaited_once()


def test_create_conversation_run_marks_failed_when_research_prompt_persistence_fails(
    conversation_runs_client,
):
    report = SimpleNamespace(id="report_123")
    created_run = ChatRunRecord.model_validate(
        {
            "id": "run_research_123",
            "conversation_id": "thread-1",
            "user_sub": "sub-testuser",
            "mode": "research",
            "research_report_id": "report_123",
            "status": "PENDING",
            "created_at": "2026-04-24T10:00:00",
            "updated_at": "2026-04-24T10:00:00",
        }
    )
    persist_submission = AsyncMock(side_effect=RuntimeError("failed to persist prompt"))
    mark_run_failed = AsyncMock(return_value=None)
    mark_report_failed = AsyncMock(return_value=None)

    with (
        patch("routers.conversations.runs._runs_enabled", return_value=True),
        patch(
            "routers.conversations.runs.ConversationService.ensure_conversation_for_submission",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "routers.conversations.runs.ConversationService.persist_submitted_messages",
            new=persist_submission,
        ),
        patch(
            "routers.conversations.runs.ResearchReportService.create_report",
            new=AsyncMock(return_value=report),
        ),
        patch(
            "routers.conversations.runs.ChatRunService.create_run",
            new=AsyncMock(return_value=created_run),
        ),
        patch(
            "routers.conversations.runs.ChatRunService.mark_failed",
            new=mark_run_failed,
        ),
        patch(
            "routers.conversations.runs.ResearchReportService.mark_failed",
            new=mark_report_failed,
        ),
    ):
        response = conversation_runs_client.post(
            "/api/conversations/runs",
            json={
                "input": {
                    "mode": "research",
                    "messages": [
                        {
                            "id": "msg-1",
                            "type": "human",
                            "content": "Create a grounded retention report.",
                        }
                    ],
                    "context_file_paths": ["docs/report.pdf"],
                },
                "config": {"configurable": {"thread_id": "thread-1"}},
            },
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "failed to persist prompt"
    mark_run_failed.assert_awaited_once_with(
        "run_research_123",
        error_message="failed to persist prompt",
    )
    mark_report_failed.assert_awaited_once_with(
        "report_123",
        error_message="failed to persist prompt",
    )


def test_create_conversation_run_rejects_duplicate_active_run(conversation_runs_client):
    with (
        patch("routers.conversations.runs._runs_enabled", return_value=True),
        patch(
            "routers.conversations.runs.ConversationService.ensure_conversation_for_submission",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "routers.conversations.runs.ChatRunService.create_run",
            new=AsyncMock(),
        ) as create_run,
    ):
        create_run.side_effect = ActiveChatRunExistsError("exists")
        response = conversation_runs_client.post(
            "/api/conversations/runs",
            json={
                "input": {
                    "messages": [
                        {"id": "msg-1", "type": "human", "content": "Hello world"}
                    ],
                    "context_file_paths": [],
                },
                "config": {"configurable": {"thread_id": "thread-1"}},
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "Conversation already has an active run"


def test_create_conversation_run_rejects_payloads_without_user_messages(
    conversation_runs_client,
):
    with (
        patch("routers.conversations.runs._runs_enabled", return_value=True),
        patch(
            "routers.conversations.runs.ConversationService.ensure_conversation_for_submission",
            new=AsyncMock(
                side_effect=ValueError(
                    "messages must include at least one user message"
                )
            ),
        ),
    ):
        response = conversation_runs_client.post(
            "/api/conversations/runs",
            json={
                "input": {
                    "messages": [
                        {"id": "msg-1", "type": "ai", "content": "Hello world"}
                    ],
                    "context_file_paths": [],
                },
                "config": {"configurable": {"thread_id": "thread-1"}},
            },
        )

    assert response.status_code == 422
    assert (
        response.json()["detail"] == "messages must include at least one user message"
    )


def test_create_conversation_run_requires_resumable_runtime(conversation_runs_client):
    with patch("routers.conversations.runs._runs_enabled", return_value=False):
        response = conversation_runs_client.post(
            "/api/conversations/runs",
            json={
                "input": {
                    "messages": [
                        {"id": "msg-1", "type": "human", "content": "Hello world"}
                    ],
                    "context_file_paths": [],
                },
                "config": {"configurable": {"thread_id": "thread-1"}},
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Resumable chat runs are not configured"


def test_get_conversation_run_returns_404_when_missing(conversation_runs_client):
    with patch(
        "routers.conversations.runs.ChatRunService.get_owned_run",
        new=AsyncMock(return_value=None),
    ):
        response = conversation_runs_client.get("/api/conversations/runs/run_missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation run not found"


def test_cancel_conversation_run_marks_owned_active_run_cancelled(
    conversation_runs_client,
):
    cancel_run = AsyncMock(return_value=_run_record(ChatRunStatus.CANCELLED))
    append_cancelled_event = AsyncMock(return_value="1713870000003-0")
    request_cancellation = MagicMock(return_value=True)
    publish_user_event = AsyncMock(return_value=None)

    with (
        patch(
            "routers.conversations.runs.ChatRunService.get_owned_run",
            new=AsyncMock(return_value=_run_record(ChatRunStatus.RUNNING)),
        ),
        patch(
            "routers.conversations.runs.ChatRunService.mark_cancelled",
            new=cancel_run,
        ),
        patch(
            "routers.conversations.runs._append_cancelled_event",
            new=append_cancelled_event,
        ),
        patch(
            "routers.conversations.runs.request_chat_run_cancellation",
            new=request_cancellation,
        ),
        patch(
            "routers.conversations.runs.publish_user_event",
            new=publish_user_event,
        ),
    ):
        response = conversation_runs_client.post(
            "/api/conversations/runs/run_123/cancel"
        )

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    append_cancelled_event.assert_awaited_once()
    cancel_run.assert_awaited_once_with(
        "run_123",
        error_message="Cancelled by user.",
        last_event_id="1713870000003-0",
    )
    request_cancellation.assert_called_once_with("run_123")
    publish_user_event.assert_awaited_once()
    assert publish_user_event.await_args.kwargs["user_sub"] == "sub-testuser"
    published = publish_user_event.await_args.kwargs["event"]
    assert published.kind == "chat.run.cancelled"
    assert published.status == "CANCELLED"
    assert published.resource_id == "thread-1"


def test_cancel_conversation_run_marks_research_report_cancelled(
    conversation_runs_client,
):
    run = ChatRunRecord.model_validate(
        {
            "id": "run_research_123",
            "conversation_id": "thread-1",
            "user_sub": "sub-testuser",
            "mode": "research",
            "research_report_id": "report_123",
            "status": "RUNNING",
            "created_at": "2026-04-24T10:00:00",
            "updated_at": "2026-04-24T10:00:00",
        }
    )
    cancel_run = AsyncMock(return_value=run.model_copy(update={"status": "CANCELLED"}))
    cancel_report = AsyncMock(return_value=None)
    publish_user_event = AsyncMock(return_value=None)

    with (
        patch(
            "routers.conversations.runs.ChatRunService.get_owned_run",
            new=AsyncMock(return_value=run),
        ),
        patch(
            "routers.conversations.runs.ChatRunService.mark_cancelled",
            new=cancel_run,
        ),
        patch(
            "routers.conversations.runs.ResearchReportService.mark_cancelled",
            new=cancel_report,
        ),
        patch(
            "routers.conversations.runs._append_cancelled_event",
            new=AsyncMock(return_value="1713950000003-0"),
        ),
        patch(
            "routers.conversations.runs.request_chat_run_cancellation",
            new=MagicMock(return_value=True),
        ),
        patch(
            "routers.conversations.runs.publish_user_event",
            new=publish_user_event,
        ),
    ):
        response = conversation_runs_client.post(
            "/api/conversations/runs/run_research_123/cancel"
        )

    assert response.status_code == 200
    cancel_report.assert_awaited_once_with(
        "report_123",
        error_message="Cancelled by user.",
    )
    published = publish_user_event.await_args.kwargs["event"]
    assert published.kind == "research.run.cancelled"
    assert published.resource_id == "thread-1"
    assert published.metadata["report_id"] == "report_123"


def test_cancel_conversation_run_returns_404_when_missing(conversation_runs_client):
    with patch(
        "routers.conversations.runs.ChatRunService.get_owned_run",
        new=AsyncMock(return_value=None),
    ):
        response = conversation_runs_client.post(
            "/api/conversations/runs/run_missing/cancel"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation run not found"


def test_cancel_conversation_run_returns_terminal_run_without_mutation(
    conversation_runs_client,
):
    append_cancelled_event = AsyncMock(return_value="1713870000003-0")
    cancel_run = AsyncMock(return_value=_run_record(ChatRunStatus.CANCELLED))
    request_cancellation = MagicMock(return_value=True)
    publish_user_event = AsyncMock(return_value=None)

    with (
        patch(
            "routers.conversations.runs.ChatRunService.get_owned_run",
            new=AsyncMock(return_value=_run_record(ChatRunStatus.COMPLETED)),
        ),
        patch(
            "routers.conversations.runs.ChatRunService.mark_cancelled",
            new=cancel_run,
        ),
        patch(
            "routers.conversations.runs._append_cancelled_event",
            new=append_cancelled_event,
        ),
        patch(
            "routers.conversations.runs.request_chat_run_cancellation",
            new=request_cancellation,
        ),
        patch(
            "routers.conversations.runs.publish_user_event",
            new=publish_user_event,
        ),
    ):
        response = conversation_runs_client.post(
            "/api/conversations/runs/run_123/cancel"
        )

    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETED"
    append_cancelled_event.assert_not_awaited()
    cancel_run.assert_not_awaited()
    request_cancellation.assert_not_called()
    publish_user_event.assert_not_awaited()


def test_cancel_conversation_run_allows_missing_cancel_event(
    conversation_runs_client,
):
    cancel_run = AsyncMock(return_value=_run_record(ChatRunStatus.CANCELLED))

    with (
        patch(
            "routers.conversations.runs.ChatRunService.get_owned_run",
            new=AsyncMock(return_value=_run_record(ChatRunStatus.RUNNING)),
        ),
        patch(
            "routers.conversations.runs.ChatRunService.mark_cancelled",
            new=cancel_run,
        ),
        patch(
            "routers.conversations.runs._append_cancelled_event",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "routers.conversations.runs.request_chat_run_cancellation",
            new=MagicMock(return_value=False),
        ),
    ):
        response = conversation_runs_client.post(
            "/api/conversations/runs/run_123/cancel"
        )

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    cancel_run.assert_awaited_once_with(
        "run_123",
        error_message="Cancelled by user.",
        last_event_id=None,
    )


@pytest.mark.asyncio
async def test_append_cancelled_event_returns_none_when_valkey_unconfigured():
    from routers.conversations.runs import _append_cancelled_event

    with patch("routers.conversations.runs.is_valkey_configured", return_value=False):
        event_id = await _append_cancelled_event(_run_record(ChatRunStatus.RUNNING))

    assert event_id is None


@pytest.mark.asyncio
async def test_append_cancelled_event_returns_none_when_client_init_fails():
    from routers.conversations.runs import _append_cancelled_event

    with (
        patch("routers.conversations.runs.is_valkey_configured", return_value=True),
        patch(
            "routers.conversations.runs.init_valkey_client",
            new=AsyncMock(return_value=None),
        ),
    ):
        event_id = await _append_cancelled_event(_run_record(ChatRunStatus.RUNNING))

    assert event_id is None


@pytest.mark.asyncio
async def test_append_cancelled_event_returns_none_when_append_raises(caplog):
    from routers.conversations.runs import _append_cancelled_event

    caplog.set_level(logging.WARNING, logger="routers.conversations.runs")

    with (
        patch("routers.conversations.runs.is_valkey_configured", return_value=True),
        patch(
            "routers.conversations.runs.init_valkey_client",
            new=AsyncMock(return_value=object()),
        ),
        patch(
            "routers.conversations.runs.ChatRunEventStore.append_event",
            new=AsyncMock(side_effect=RuntimeError("valkey unavailable")),
        ),
    ):
        event_id = await _append_cancelled_event(_run_record(ChatRunStatus.RUNNING))

    assert event_id is None
    assert "Failed to append cancellation event for run_123" in caplog.text
    assert "RuntimeError: valkey unavailable" in caplog.text


def test_stream_conversation_run_hides_foreign_or_missing_runs(
    conversation_runs_client,
):
    with patch(
        "routers.conversations.runs.ChatRunService.get_owned_run",
        new=AsyncMock(return_value=None),
    ):
        response = conversation_runs_client.get(
            "/api/conversations/runs/run_foreign/stream"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation run not found"


def test_stream_conversation_run_requires_valkey_configuration(
    conversation_runs_client,
):
    with (
        patch(
            "routers.conversations.runs.ChatRunService.get_owned_run",
            new=AsyncMock(return_value=_run_record(ChatRunStatus.RUNNING)),
        ),
        patch("routers.conversations.runs.is_valkey_configured", return_value=False),
    ):
        response = conversation_runs_client.get(
            "/api/conversations/runs/run_123/stream"
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Resumable chat runs are not configured"


def test_stream_conversation_run_returns_503_when_valkey_client_unavailable(
    conversation_runs_client,
):
    with (
        patch(
            "routers.conversations.runs.ChatRunService.get_owned_run",
            new=AsyncMock(return_value=_run_record(ChatRunStatus.RUNNING)),
        ),
        patch("routers.conversations.runs.is_valkey_configured", return_value=True),
        patch(
            "routers.conversations.runs.init_valkey_client",
            new=AsyncMock(return_value=None),
        ),
    ):
        response = conversation_runs_client.get(
            "/api/conversations/runs/run_123/stream"
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Resumable chat runs are not configured"


def test_stream_conversation_run_replays_existing_events(conversation_runs_client):
    replayed = [
        _event("messages", "1713870000000-0", {"delta": "hello"}),
        _event("done", "1713870000001-0", {"status": "COMPLETED"}),
    ]

    with (
        patch(
            "routers.conversations.runs.ChatRunService.get_owned_run",
            new=AsyncMock(return_value=_run_record(ChatRunStatus.COMPLETED)),
        ),
        patch("routers.conversations.runs.is_valkey_configured", return_value=True),
        patch(
            "routers.conversations.runs.init_valkey_client",
            new=AsyncMock(return_value=object()),
        ),
        patch(
            "routers.conversations.runs.ChatRunEventStore.replay_events",
            new=AsyncMock(return_value=replayed),
        ),
    ):
        response = conversation_runs_client.get(
            "/api/conversations/runs/run_123/stream"
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "id: 1713870000000-0" in response.text
    assert "event: messages" in response.text
    assert "event: done" in response.text


def test_stream_conversation_run_forwards_after_query_to_replay(
    conversation_runs_client,
):
    replay_events = AsyncMock(
        return_value=[_event("done", "1713870000002-0", {"status": "COMPLETED"})]
    )

    with (
        patch(
            "routers.conversations.runs.ChatRunService.get_owned_run",
            new=AsyncMock(return_value=_run_record(ChatRunStatus.COMPLETED)),
        ),
        patch("routers.conversations.runs.is_valkey_configured", return_value=True),
        patch(
            "routers.conversations.runs.init_valkey_client",
            new=AsyncMock(return_value=object()),
        ),
        patch(
            "routers.conversations.runs.ChatRunEventStore.replay_events",
            new=replay_events,
        ),
    ):
        response = conversation_runs_client.get(
            "/api/conversations/runs/run_123/stream?after=1713870000001-0"
        )

    assert response.status_code == 200
    assert "id: 1713870000002-0" in response.text
    replay_events.assert_awaited_once_with(
        run_id="run_123",
        after_id="1713870000001-0",
        limit=1000,
    )


def test_stream_conversation_run_accepts_last_event_id_header(conversation_runs_client):
    replay_events = AsyncMock(
        return_value=[_event("done", "1713870000002-0", {"status": "COMPLETED"})]
    )

    with (
        patch(
            "routers.conversations.runs.ChatRunService.get_owned_run",
            new=AsyncMock(return_value=_run_record(ChatRunStatus.COMPLETED)),
        ),
        patch("routers.conversations.runs.is_valkey_configured", return_value=True),
        patch(
            "routers.conversations.runs.init_valkey_client",
            new=AsyncMock(return_value=object()),
        ),
        patch(
            "routers.conversations.runs.ChatRunEventStore.replay_events",
            new=replay_events,
        ),
    ):
        response = conversation_runs_client.get(
            "/api/conversations/runs/run_123/stream",
            headers={"Last-Event-ID": "1713870000001-0"},
        )

    assert response.status_code == 200
    replay_events.assert_awaited_once_with(
        run_id="run_123",
        after_id="1713870000001-0",
        limit=1000,
    )


def test_stream_conversation_run_replays_terminal_events_across_pages(
    conversation_runs_client,
):
    replay_events = AsyncMock(
        side_effect=[
            [_event("messages", "1713870000000-0", {"delta": "hello"})],
            [_event("messages", "1713870000001-0", {"delta": " again"})],
            [_event("done", "1713870000002-0", {"status": "COMPLETED"})],
        ]
    )

    with (
        patch(
            "routers.conversations.runs.ChatRunService.get_owned_run",
            new=AsyncMock(return_value=_run_record(ChatRunStatus.COMPLETED)),
        ),
        patch("routers.conversations.runs.is_valkey_configured", return_value=True),
        patch(
            "routers.conversations.runs.init_valkey_client",
            new=AsyncMock(return_value=object()),
        ),
        patch(
            "routers.conversations.runs.get_settings",
            return_value=SimpleNamespace(CHAT_RUN_MAX_REPLAY_EVENTS=1),
        ),
        patch(
            "routers.conversations.runs.ChatRunEventStore.replay_events",
            new=replay_events,
        ),
    ):
        response = conversation_runs_client.get(
            "/api/conversations/runs/run_123/stream"
        )

    assert response.status_code == 200
    assert "id: 1713870000000-0" in response.text
    assert "id: 1713870000001-0" in response.text
    assert "id: 1713870000002-0" in response.text
    assert replay_events.await_args_list == [
        call(run_id="run_123", after_id=None, limit=1),
        call(run_id="run_123", after_id="1713870000000-0", limit=1),
        call(run_id="run_123", after_id="1713870000001-0", limit=1),
    ]


def test_stream_conversation_run_replays_late_terminal_events(conversation_runs_client):
    running_then_completed = [
        _run_record(ChatRunStatus.RUNNING),
        _run_record(ChatRunStatus.COMPLETED),
    ]
    get_owned_run = AsyncMock(side_effect=running_then_completed)
    replay_events = AsyncMock(
        side_effect=[
            [],
            [_event("done", "1713870000002-0", {"status": "COMPLETED"})],
        ]
    )

    with (
        patch(
            "routers.conversations.runs.ChatRunService.get_owned_run",
            new=get_owned_run,
        ),
        patch("routers.conversations.runs.is_valkey_configured", return_value=True),
        patch(
            "routers.conversations.runs.init_valkey_client",
            new=AsyncMock(return_value=object()),
        ),
        patch(
            "routers.conversations.runs.ChatRunEventStore.replay_events",
            new=replay_events,
        ),
        patch(
            "routers.conversations.runs.ChatRunEventStore.read_next_events",
            new=AsyncMock(return_value=[]),
        ),
    ):
        response = conversation_runs_client.get(
            "/api/conversations/runs/run_123/stream"
        )

    assert response.status_code == 200
    assert "event: done" in response.text
    assert "id: 1713870000002-0" in response.text
    assert replay_events.await_count == 2


def test_stream_conversation_run_tails_live_events_until_done(
    conversation_runs_client,
):
    live_events = [
        _event("messages", "1713870000001-0", {"delta": "hello"}),
        _event("done", "1713870000002-0", {"status": "COMPLETED"}),
    ]

    with (
        patch(
            "routers.conversations.runs.ChatRunService.get_owned_run",
            new=AsyncMock(return_value=_run_record(ChatRunStatus.RUNNING)),
        ),
        patch("routers.conversations.runs.is_valkey_configured", return_value=True),
        patch(
            "routers.conversations.runs.init_valkey_client",
            new=AsyncMock(return_value=object()),
        ),
        patch(
            "routers.conversations.runs.ChatRunEventStore.replay_events",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "routers.conversations.runs.ChatRunEventStore.read_next_events",
            new=AsyncMock(return_value=live_events),
        ),
    ):
        response = conversation_runs_client.get(
            "/api/conversations/runs/run_123/stream"
        )

    assert response.status_code == 200
    assert "id: 1713870000001-0" in response.text
    assert "event: messages" in response.text
    assert "event: done" in response.text


def test_stream_conversation_run_stops_when_run_disappears_while_tailing(
    conversation_runs_client,
):
    get_owned_run = AsyncMock(
        side_effect=[
            _run_record(ChatRunStatus.RUNNING),
            None,
        ]
    )

    with (
        patch(
            "routers.conversations.runs.ChatRunService.get_owned_run",
            new=get_owned_run,
        ),
        patch("routers.conversations.runs.is_valkey_configured", return_value=True),
        patch(
            "routers.conversations.runs.init_valkey_client",
            new=AsyncMock(return_value=object()),
        ),
        patch(
            "routers.conversations.runs.ChatRunEventStore.replay_events",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "routers.conversations.runs.ChatRunEventStore.read_next_events",
            new=AsyncMock(return_value=[]),
        ),
    ):
        response = conversation_runs_client.get(
            "/api/conversations/runs/run_123/stream"
        )

    assert response.status_code == 200
    assert response.text == ""
    assert get_owned_run.await_count == 2


def test_stream_conversation_run_returns_empty_stream_for_terminal_run_without_events(
    conversation_runs_client,
):
    with (
        patch(
            "routers.conversations.runs.ChatRunService.get_owned_run",
            new=AsyncMock(return_value=_run_record(ChatRunStatus.COMPLETED)),
        ),
        patch("routers.conversations.runs.is_valkey_configured", return_value=True),
        patch(
            "routers.conversations.runs.init_valkey_client",
            new=AsyncMock(return_value=object()),
        ),
        patch(
            "routers.conversations.runs.ChatRunEventStore.replay_events",
            new=AsyncMock(return_value=[]),
        ),
    ):
        response = conversation_runs_client.get(
            "/api/conversations/runs/run_123/stream"
        )

    assert response.status_code == 200
    assert response.text == ""


def test_stream_conversation_run_clamps_replay_limit_to_one(
    conversation_runs_client,
):
    replay_events = AsyncMock(
        return_value=[_event("done", "1713870000002-0", {"status": "COMPLETED"})]
    )

    with (
        patch(
            "routers.conversations.runs.ChatRunService.get_owned_run",
            new=AsyncMock(return_value=_run_record(ChatRunStatus.COMPLETED)),
        ),
        patch("routers.conversations.runs.is_valkey_configured", return_value=True),
        patch(
            "routers.conversations.runs.init_valkey_client",
            new=AsyncMock(return_value=object()),
        ),
        patch(
            "routers.conversations.runs.get_settings",
            return_value=SimpleNamespace(CHAT_RUN_MAX_REPLAY_EVENTS=0),
        ),
        patch(
            "routers.conversations.runs.ChatRunEventStore.replay_events",
            new=replay_events,
        ),
    ):
        response = conversation_runs_client.get(
            "/api/conversations/runs/run_123/stream"
        )

    assert response.status_code == 200
    replay_events.assert_awaited_once_with(
        run_id="run_123",
        after_id=None,
        limit=1,
    )
