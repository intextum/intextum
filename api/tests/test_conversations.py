"""Tests for the LangGraph-thread-backed conversations router."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage

from auth.dependencies import require_user
from models.chat.runs import ChatRunRecord
from models.enums import ChatRunStatus
from chat.snapshot import ChatThreadSnapshot
from chat.transport import ChatStreamServiceRequest
from database import get_db
from models.chat import ChatStreamMessage
from models.user import User
from routers.conversations.helpers import get_conversation_service
from routers.conversations.router import router as conversations_router
from services.conversation import ConversationService


@pytest.fixture
def conversations_client():
    """FastAPI test client with conversation router dependency overrides."""
    app = FastAPI()
    app.include_router(conversations_router, prefix="/api/conversations")

    user = User(username="testuser", sub="sub-testuser")
    mock_db = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

    app.dependency_overrides.clear()


def test_get_conversation_returns_404_when_missing(conversations_client):
    """GET /api/conversations/{id} returns 404 for unknown conversations."""
    mock_service = AsyncMock()
    mock_service.get_conversation.return_value = None

    app = conversations_client.app
    app.dependency_overrides[get_conversation_service] = lambda: mock_service

    response = conversations_client.get("/api/conversations/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"


def test_delete_all_conversations_returns_deleted_count(conversations_client):
    """DELETE /api/conversations removes all conversations for current user."""
    mock_service = AsyncMock()
    mock_service.list_conversation_ids.return_value = ["conv-1", "conv-2", "conv-3"]
    mock_service.delete_conversations_by_ids.return_value = 3

    app = conversations_client.app
    app.dependency_overrides[get_conversation_service] = lambda: mock_service

    response = conversations_client.delete("/api/conversations/")

    assert response.status_code == 200
    assert response.json() == {"deleted_count": 3}
    mock_service.delete_conversations_by_ids.assert_awaited_once_with(
        ["conv-1", "conv-2", "conv-3"]
    )


def test_import_conversation_returns_created_conversation_id(conversations_client):
    """POST /api/conversations/import materializes a temporary transcript."""
    mock_service = AsyncMock()
    mock_service.import_transcript.return_value = "thread-imported"

    app = conversations_client.app
    app.dependency_overrides[get_conversation_service] = lambda: mock_service

    response = conversations_client.post(
        "/api/conversations/import",
        json={
            "title": "Imported chat",
            "context_file_paths": ["documents/report.pdf"],
            "messages": [
                {"id": "msg-1", "type": "human", "content": "Summarize"},
                {
                    "id": "msg-2",
                    "type": "ai",
                    "content": "Summary [1]",
                    "additional_kwargs": {
                        "sources": [
                            {
                                "file_path": "documents/report.pdf",
                                "citation_index": 1,
                                "doc_refs": ["ref-1"],
                            }
                        ]
                    },
                },
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == {"conversation_id": "thread-imported"}
    mock_service.import_transcript.assert_awaited_once()


def test_regenerate_conversation_message_creates_run(conversations_client):
    """POST /messages/{id}/regenerate rewinds the transcript and queues a run."""
    mock_service = AsyncMock()
    mock_service.prepare_message_regeneration.return_value = SimpleNamespace(
        messages=[ChatStreamMessage(id="user-2", type="human", content="Try again")],
        context_file_paths=["documents/report.pdf"],
    )
    created_run = ChatRunRecord.model_validate(
        {
            "id": "run_1",
            "conversation_id": "thread-1",
            "user_sub": "sub-testuser",
            "status": ChatRunStatus.PENDING.value,
            "created_at": _utc(2026, 4, 23, 8),
            "updated_at": _utc(2026, 4, 23, 8),
        }
    )
    run_service = AsyncMock()
    run_service.has_active_run.return_value = False
    run_service.create_run.return_value = created_run

    app = conversations_client.app
    app.dependency_overrides[get_conversation_service] = lambda: mock_service

    with (
        patch("routers.conversations.router._runs_enabled", return_value=True),
        patch("routers.conversations.router.ChatRunService", return_value=run_service),
    ):
        response = conversations_client.post(
            "/api/conversations/thread-1/messages/assistant-2/regenerate"
        )

    assert response.status_code == 200
    assert response.json()["run_id"] == "run_1"
    mock_service.prepare_message_regeneration.assert_awaited_once_with(
        "thread-1",
        "assistant-2",
    )
    run_service.create_run.assert_awaited_once()


def test_regenerate_conversation_message_rejects_active_run(conversations_client):
    """Regenerate should not mutate state while a run is already active."""
    mock_service = AsyncMock()
    run_service = AsyncMock()
    run_service.has_active_run.return_value = True

    app = conversations_client.app
    app.dependency_overrides[get_conversation_service] = lambda: mock_service

    with (
        patch("routers.conversations.router._runs_enabled", return_value=True),
        patch("routers.conversations.router.ChatRunService", return_value=run_service),
    ):
        response = conversations_client.post(
            "/api/conversations/thread-1/messages/assistant-2/regenerate"
        )

    assert response.status_code == 409
    mock_service.prepare_message_regeneration.assert_not_awaited()


def test_regenerate_conversation_message_returns_404_for_non_owned_conversation(
    conversations_client,
):
    """A missing/non-owned conversation should not create a run."""
    mock_service = AsyncMock()
    mock_service.prepare_message_regeneration.return_value = None
    run_service = AsyncMock()
    run_service.has_active_run.return_value = False

    app = conversations_client.app
    app.dependency_overrides[get_conversation_service] = lambda: mock_service

    with (
        patch("routers.conversations.router._runs_enabled", return_value=True),
        patch("routers.conversations.router.ChatRunService", return_value=run_service),
    ):
        response = conversations_client.post(
            "/api/conversations/thread-1/messages/assistant-2/regenerate"
        )

    assert response.status_code == 404
    run_service.create_run.assert_not_awaited()


def test_regenerate_conversation_message_returns_422_for_invalid_message(
    conversations_client,
):
    """Service validation errors should be returned before run creation."""
    mock_service = AsyncMock()
    mock_service.prepare_message_regeneration.side_effect = ValueError(
        "Only the latest assistant message can be regenerated"
    )
    run_service = AsyncMock()
    run_service.has_active_run.return_value = False

    app = conversations_client.app
    app.dependency_overrides[get_conversation_service] = lambda: mock_service

    with (
        patch("routers.conversations.router._runs_enabled", return_value=True),
        patch("routers.conversations.router.ChatRunService", return_value=run_service),
    ):
        response = conversations_client.post(
            "/api/conversations/thread-1/messages/assistant-1/regenerate"
        )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Only the latest assistant message can be regenerated"
    )
    run_service.create_run.assert_not_awaited()


def test_delete_conversation_removes_checkpointer_rows():
    """Conversation deletion should remove metadata and LangGraph thread state."""

    async def run_test():
        user = User(username="testuser", sub="sub-testuser")
        service = ConversationService(db=AsyncMock(), user=user)
        record = _record("thread-1")

        with (
            patch.object(
                service.record_service,
                "get_owned_conversation",
                new=AsyncMock(return_value=record),
            ),
            patch.object(
                service,
                "_load_owned_snapshot",
                new=AsyncMock(return_value=ChatThreadSnapshot(user_sub="sub-testuser")),
            ),
            patch.object(
                service.thread_manager,
                "delete_thread",
                new=AsyncMock(return_value=None),
            ) as delete_thread,
            patch.object(
                service.record_service,
                "delete_owned_conversation",
                new=AsyncMock(return_value=True),
            ) as delete_record,
        ):
            deleted = await service.delete_conversation("thread-1")

        assert deleted is True
        delete_thread.assert_awaited_once_with("thread-1")
        delete_record.assert_awaited_once_with("thread-1", "sub-testuser")

    asyncio.run(run_test())


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc).replace(tzinfo=None)


def _record(
    conversation_id: str,
    *,
    title: str | None = None,
    user_sub: str = "sub-testuser",
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
):
    return SimpleNamespace(
        id=conversation_id,
        title=title,
        user_sub=user_sub,
        created_at=created_at or _utc(2026, 4, 23, 8),
        updated_at=updated_at or _utc(2026, 4, 23, 8),
    )


@pytest.mark.asyncio
async def test_get_conversation_returns_placeholder_when_metadata_exists_without_snapshot():
    user = User(username="testuser", sub="sub-testuser")
    service = ConversationService(db=AsyncMock(), user=user)
    record = _record(
        "thread-pending",
        title="Pending chat",
        created_at=_utc(2026, 4, 23, 10),
        updated_at=_utc(2026, 4, 23, 11),
    )

    with (
        patch.object(
            service.record_service,
            "get_owned_conversation",
            new=AsyncMock(return_value=record),
        ),
        patch.object(service, "_load_owned_snapshot", new=AsyncMock(return_value=None)),
    ):
        detail = await service.get_conversation("thread-pending")

    assert detail is not None
    assert detail.id == "thread-pending"
    assert detail.title == "Pending chat"
    assert detail.messages == []
    assert detail.created_at == "2026-04-23T10:00:00+00:00"
    assert detail.updated_at == "2026-04-23T11:00:00+00:00"


@pytest.mark.asyncio
async def test_ensure_conversation_for_submission_materializes_new_conversation_row():
    user = User(username="testuser", sub="sub-testuser")
    service = ConversationService(db=AsyncMock(), user=user)
    request = ChatStreamServiceRequest(
        conversation_id="thread-new",
        messages=[ChatStreamMessage(id="msg-1", type="human", content="Need a plan")],
        context_file_paths=["documents/report.pdf"],
    )

    with (
        patch.object(
            service.record_service,
            "get_conversation",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            service.record_service,
            "upsert_conversation",
            new=AsyncMock(return_value=_record("thread-new")),
        ) as upsert_conversation,
    ):
        await service.ensure_conversation_for_submission(
            request,
            now="2026-04-23T12:00:00+00:00",
        )

    upsert_conversation.assert_awaited_once_with(
        conversation_id="thread-new",
        user_sub="sub-testuser",
        title="Need a plan",
        created_at="2026-04-23T12:00:00+00:00",
        updated_at="2026-04-23T12:00:00+00:00",
    )


@pytest.mark.asyncio
async def test_ensure_conversation_for_submission_rejects_payloads_without_user_messages():
    user = User(username="testuser", sub="sub-testuser")
    service = ConversationService(db=AsyncMock(), user=user)
    request = ChatStreamServiceRequest(
        conversation_id="thread-invalid",
        messages=[ChatStreamMessage(id="msg-1", type="ai", content="Hello")],
        context_file_paths=[],
    )

    with pytest.raises(
        ValueError, match="messages must include at least one user message"
    ):
        await service.ensure_conversation_for_submission(request)


@pytest.mark.asyncio
async def test_list_conversations_marks_active_run_status_and_bumps_updated_at():
    user = User(username="testuser", sub="sub-testuser")
    service = ConversationService(db=AsyncMock(), user=user)
    record = _record(
        "thread-1",
        title="Existing chat",
        created_at=_utc(2026, 4, 23, 8),
        updated_at=_utc(2026, 4, 23, 8),
    )
    active_run = ChatRunRecord.model_validate(
        {
            "id": "run_1",
            "conversation_id": "thread-1",
            "user_sub": "sub-testuser",
            "status": ChatRunStatus.RUNNING.value,
            "created_at": _utc(2026, 4, 23, 8),
            "updated_at": _utc(2026, 4, 23, 9),
        }
    )

    with (
        patch.object(
            service.record_service,
            "list_owned_conversations",
            new=AsyncMock(return_value=[record]),
        ),
        patch(
            "services.conversation.ChatRunService.list_active_runs_for_user",
            new=AsyncMock(return_value=[active_run]),
        ),
    ):
        conversations, total = await service.list_conversations()

    assert total == 1
    assert conversations[0].id == "thread-1"
    assert conversations[0].active_run_status == "RUNNING"
    assert conversations[0].updated_at == "2026-04-23T09:00:00+00:00"


@pytest.mark.asyncio
async def test_list_conversations_returns_empty_when_metadata_is_empty():
    user = User(username="testuser", sub="sub-testuser")
    service = ConversationService(db=AsyncMock(), user=user)

    with (
        patch.object(
            service.record_service,
            "list_owned_conversations",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "services.conversation.ChatRunService.list_active_runs_for_user",
            new=AsyncMock(return_value=[]),
        ),
    ):
        conversations, total = await service.list_conversations()

    assert conversations == []
    assert total == 0


@pytest.mark.asyncio
async def test_get_conversation_returns_none_without_metadata_even_if_snapshot_exists():
    user = User(username="testuser", sub="sub-testuser")
    service = ConversationService(db=AsyncMock(), user=user)

    with (
        patch.object(
            service.record_service,
            "get_owned_conversation",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            service,
            "_load_owned_snapshot",
            new=AsyncMock(return_value=ChatThreadSnapshot(user_sub="sub-testuser")),
        ),
    ):
        detail = await service.get_conversation("thread-without-record")

    assert detail is None


@pytest.mark.asyncio
async def test_update_conversation_returns_none_without_metadata_even_if_snapshot_exists():
    user = User(username="testuser", sub="sub-testuser")
    service = ConversationService(db=AsyncMock(), user=user)

    with (
        patch.object(
            service.record_service,
            "get_owned_conversation",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            service,
            "_load_owned_snapshot",
            new=AsyncMock(return_value=ChatThreadSnapshot(user_sub="sub-testuser")),
        ) as load_snapshot,
        patch.object(
            service.thread_manager,
            "update_state",
            new=AsyncMock(return_value=None),
        ) as update_state,
    ):
        summary = await service.update_conversation("thread-without-record", "Renamed")

    assert summary is None
    load_snapshot.assert_not_awaited()
    update_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_import_transcript_persists_full_transcript():
    user = User(username="testuser", sub="sub-testuser")
    service = ConversationService(db=AsyncMock(), user=user)

    with (
        patch.object(
            service.record_service,
            "upsert_conversation",
            new=AsyncMock(return_value=_record("thread-imported")),
        ) as upsert_conversation,
        patch.object(
            service.thread_manager,
            "update_state",
            new=AsyncMock(return_value=None),
        ) as update_state,
        patch("services.conversation.uuid4", return_value="thread-imported"),
    ):
        conversation_id = await service.import_transcript(
            title=None,
            context_file_paths=["documents/report.pdf"],
            messages=[
                ChatStreamMessage(id="msg-1", type="human", content="Summarize"),
                ChatStreamMessage(
                    id="msg-2",
                    type="ai",
                    content="Summary [1]",
                    additional_kwargs={
                        "sources": [
                            {
                                "file_path": "documents/report.pdf",
                                "citation_index": 1,
                                "doc_refs": ["ref-1"],
                            }
                        ]
                    },
                ),
            ],
            now="2026-04-23T12:00:00+00:00",
        )

    assert conversation_id == "thread-imported"
    upsert_conversation.assert_awaited_once_with(
        conversation_id="thread-imported",
        user_sub="sub-testuser",
        title="Summarize",
        created_at="2026-04-23T12:00:00+00:00",
        updated_at="2026-04-23T12:00:00+00:00",
    )
    patch_arg = update_state.await_args.args[1]
    assert [message.content for message in patch_arg.messages] == [
        "Summarize",
        "Summary [1]",
    ]
    assert patch_arg.context_file_paths == ["documents/report.pdf"]
    assert patch_arg.messages[1].additional_kwargs["sources"][0]["doc_refs"] == [
        "ref-1"
    ]


@pytest.mark.asyncio
async def test_prepare_message_regeneration_rewinds_latest_assistant():
    user = User(username="testuser", sub="sub-testuser")
    service = ConversationService(db=AsyncMock(), user=user)
    record = _record("thread-1", title="Existing chat")
    snapshot = ChatThreadSnapshot(
        user_sub="sub-testuser",
        title="Existing chat",
        context_file_paths=["documents/report.pdf"],
        messages=[
            HumanMessage(id="user-1", content="Hello"),
            AIMessage(id="assistant-1", content="Hi"),
            HumanMessage(
                id="user-2",
                content="Summarize this",
                additional_kwargs={
                    "created_at": "2026-04-23T12:00:00+00:00",
                    "context_file_paths": ["documents/report.pdf"],
                },
            ),
            AIMessage(id="assistant-2", content="Summary"),
        ],
    )

    with (
        patch.object(
            service.record_service,
            "get_owned_conversation",
            new=AsyncMock(return_value=record),
        ),
        patch.object(
            service, "_load_owned_snapshot", new=AsyncMock(return_value=snapshot)
        ),
        patch.object(
            service.thread_manager,
            "update_state",
            new=AsyncMock(return_value=None),
        ) as update_state,
        patch.object(
            service.record_service,
            "upsert_conversation",
            new=AsyncMock(return_value=record),
        ) as upsert_conversation,
    ):
        regeneration = await service.prepare_message_regeneration(
            "thread-1",
            "assistant-2",
            now="2026-04-23T12:30:00+00:00",
        )

    assert regeneration is not None
    assert regeneration.context_file_paths == ["documents/report.pdf"]
    assert regeneration.messages[0].id == "user-2"
    assert regeneration.messages[0].content == "Summarize this"
    assert regeneration.messages[0].additional_kwargs["created_at"] == (
        "2026-04-23T12:00:00+00:00"
    )
    patch_arg = update_state.await_args.args[1]
    assert [message.id for message in patch_arg.messages] == ["assistant-2"]
    assert all(isinstance(message, RemoveMessage) for message in patch_arg.messages)
    assert patch_arg.updated_at == "2026-04-23T12:30:00+00:00"
    assert update_state.await_args.kwargs["as_node"] == "tools"
    upsert_conversation.assert_awaited_once()


@pytest.mark.asyncio
async def test_prepare_message_regeneration_removes_hidden_trailing_messages():
    user = User(username="testuser", sub="sub-testuser")
    service = ConversationService(db=AsyncMock(), user=user)
    snapshot = ChatThreadSnapshot(
        user_sub="sub-testuser",
        context_file_paths=[],
        messages=[
            HumanMessage(id="user-1", content="Hello"),
            AIMessage(id="assistant-1", content="Hi"),
            AIMessage(id="assistant-hidden", content=""),
        ],
    )

    with (
        patch.object(
            service.record_service,
            "get_owned_conversation",
            new=AsyncMock(return_value=_record("thread-1")),
        ),
        patch.object(
            service, "_load_owned_snapshot", new=AsyncMock(return_value=snapshot)
        ),
        patch.object(
            service.thread_manager,
            "update_state",
            new=AsyncMock(return_value=None),
        ) as update_state,
        patch.object(
            service.record_service,
            "upsert_conversation",
            new=AsyncMock(return_value=_record("thread-1")),
        ),
    ):
        regeneration = await service.prepare_message_regeneration(
            "thread-1",
            "assistant-1",
            now="2026-04-23T12:30:00+00:00",
        )

    assert regeneration is not None
    patch_arg = update_state.await_args.args[1]
    assert [message.id for message in patch_arg.messages] == [
        "assistant-1",
        "assistant-hidden",
    ]
    assert update_state.await_args.kwargs["as_node"] == "tools"


@pytest.mark.asyncio
async def test_prepare_message_regeneration_rejects_unknown_message():
    user = User(username="testuser", sub="sub-testuser")
    service = ConversationService(db=AsyncMock(), user=user)
    snapshot = ChatThreadSnapshot(
        user_sub="sub-testuser",
        messages=[
            HumanMessage(id="user-1", content="Hello"),
            AIMessage(id="assistant-1", content="Hi"),
        ],
    )

    with (
        patch.object(
            service.record_service,
            "get_owned_conversation",
            new=AsyncMock(return_value=_record("thread-1")),
        ),
        patch.object(
            service, "_load_owned_snapshot", new=AsyncMock(return_value=snapshot)
        ),
    ):
        with pytest.raises(ValueError, match="Message not found"):
            await service.prepare_message_regeneration("thread-1", "missing")


@pytest.mark.asyncio
async def test_prepare_message_regeneration_rejects_non_latest_assistant():
    user = User(username="testuser", sub="sub-testuser")
    service = ConversationService(db=AsyncMock(), user=user)
    snapshot = ChatThreadSnapshot(
        user_sub="sub-testuser",
        messages=[
            HumanMessage(id="user-1", content="Hello"),
            AIMessage(id="assistant-1", content="Hi"),
            HumanMessage(id="user-2", content="Continue"),
            AIMessage(id="assistant-2", content="Done"),
        ],
    )

    with (
        patch.object(
            service.record_service,
            "get_owned_conversation",
            new=AsyncMock(return_value=_record("thread-1")),
        ),
        patch.object(
            service, "_load_owned_snapshot", new=AsyncMock(return_value=snapshot)
        ),
    ):
        with pytest.raises(ValueError, match="Only the latest assistant message"):
            await service.prepare_message_regeneration("thread-1", "assistant-1")


@pytest.mark.asyncio
async def test_prepare_message_regeneration_rejects_user_message():
    user = User(username="testuser", sub="sub-testuser")
    service = ConversationService(db=AsyncMock(), user=user)
    snapshot = ChatThreadSnapshot(
        user_sub="sub-testuser",
        messages=[
            HumanMessage(id="user-1", content="Hello"),
            AIMessage(id="assistant-1", content="Hi"),
        ],
    )

    with (
        patch.object(
            service.record_service,
            "get_owned_conversation",
            new=AsyncMock(return_value=_record("thread-1")),
        ),
        patch.object(
            service, "_load_owned_snapshot", new=AsyncMock(return_value=snapshot)
        ),
    ):
        with pytest.raises(ValueError, match="Only assistant messages"):
            await service.prepare_message_regeneration("thread-1", "user-1")


@pytest.mark.asyncio
async def test_prepare_message_regeneration_rejects_assistant_without_user_prompt():
    user = User(username="testuser", sub="sub-testuser")
    service = ConversationService(db=AsyncMock(), user=user)
    snapshot = ChatThreadSnapshot(
        user_sub="sub-testuser",
        messages=[AIMessage(id="assistant-1", content="Hi")],
    )

    with (
        patch.object(
            service.record_service,
            "get_owned_conversation",
            new=AsyncMock(return_value=_record("thread-1")),
        ),
        patch.object(
            service, "_load_owned_snapshot", new=AsyncMock(return_value=snapshot)
        ),
    ):
        with pytest.raises(ValueError, match="no preceding user message"):
            await service.prepare_message_regeneration("thread-1", "assistant-1")
