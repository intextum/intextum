"""Tests for background resumable chat run execution."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager, suppress
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from chat.runner import core as runner
from chat.runner.support import payload_user
from models.chat.runs import ChatRunRequestPayload
from models.enums import ChatRunStatus, ConversationRunMode


class _SessionContext:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _Graph:
    def __init__(self, *, parts=None, exc=None):
        self.parts = [] if parts is None else parts
        self.exc = exc

    def astream(self, *args, **kwargs):
        async def _events():
            if self.exc is not None:
                raise self.exc
            for part in self.parts:
                yield part

        return _events()


@pytest.fixture(autouse=True)
def clear_active_run_tasks():
    """Keep the module-level cancellation registry isolated between tests."""
    runner._active_run_tasks.clear()
    yield
    for task in list(runner._active_run_tasks.values()):
        task.cancel()
    runner._active_run_tasks.clear()


def _session_factory(db=None):
    db = object() if db is None else db

    def _factory():
        return _SessionContext(db)

    return _factory


def _settings(**overrides):
    values = {
        "CHAT_RUN_HEARTBEAT_SECONDS": 0,
        "CHAT_RUN_CLAIM_TIMEOUT_SECONDS": 300,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _payload() -> ChatRunRequestPayload:
    return ChatRunRequestPayload.model_validate(
        {
            "conversation_id": "thread-1",
            "user": {
                "username": "testuser",
                "sub": "sub-testuser",
                "is_admin": True,
            },
            "messages": [],
            "context_file_paths": [],
        }
    )


def _research_payload() -> ChatRunRequestPayload:
    return ChatRunRequestPayload.model_validate(
        {
            "conversation_id": "thread-1",
            "mode": ConversationRunMode.RESEARCH,
            "research_report_id": "report_123",
            "user": {
                "username": "testuser",
                "sub": "sub-testuser",
                "is_admin": True,
            },
            "messages": [
                {
                    "id": "msg-1",
                    "type": "human",
                    "content": "Create a grounded retention report.",
                }
            ],
            "context_file_paths": ["docs/report.pdf"],
        }
    )


def _prepared_run(graph: _Graph):
    return SimpleNamespace(
        conversation_id="thread-1",
        graph_input={"messages": []},
        thread_manager=SimpleNamespace(graph=graph),
    )


def _event_id(event_id: str):
    return SimpleNamespace(event_id=event_id)


def _event_store(*event_ids: str):
    return SimpleNamespace(
        append_event=AsyncMock(
            side_effect=[_event_id(event_id) for event_id in event_ids]
        )
    )


def _service(payload=None):
    return SimpleNamespace(
        get_request_payload=AsyncMock(
            return_value=_payload() if payload is None else payload
        ),
        get_run_status=AsyncMock(return_value=ChatRunStatus.RUNNING),
        touch_last_event=AsyncMock(),
        mark_completed=AsyncMock(),
        mark_failed=AsyncMock(),
        mark_cancelled=AsyncMock(),
    )


@contextmanager
def _patch_execution_dependencies(service, graph, *, prepare_side_effect=None):
    prepare_run = AsyncMock(
        side_effect=prepare_side_effect,
        return_value=_prepared_run(graph),
    )
    with (
        patch("chat.runner.core.ChatRunService", return_value=service),
        patch("chat.runner.core.get_settings", return_value=_settings()),
        patch(
            "chat.runner.core.AiSettingsService",
            return_value=SimpleNamespace(
                get_effective_settings=AsyncMock(return_value=None)
            ),
        ),
        patch("chat.runner.core.ChatThreadManager", return_value=object()),
        patch("chat.runner.core.prepare_chat_stream_run", new=prepare_run),
    ):
        yield prepare_run


def test_request_chat_run_cancellation_returns_false_without_active_task():
    assert runner.request_chat_run_cancellation("run_missing") is False


def test_payload_user_preserves_admin_flag_for_acl_evaluation():
    user = payload_user(_payload())

    assert user.is_admin is True


@pytest.mark.asyncio
async def test_request_chat_run_cancellation_cancels_active_task():
    async def _sleep_forever():
        await asyncio.sleep(60)

    task = asyncio.create_task(_sleep_forever())
    runner._active_run_tasks["run_123"] = task

    assert runner.request_chat_run_cancellation("run_123") is True
    with suppress(asyncio.CancelledError):
        await task
    assert task.cancelled()


@pytest.mark.asyncio
async def test_execute_chat_run_success_appends_stream_events_and_done():
    service = _service()
    graph = _Graph(
        parts=[
            {"type": "messages", "data": {"delta": "hello"}},
            {"type": "values", "data": {"messages": []}},
            {"type": "ignored", "data": {"unused": True}},
        ]
    )
    event_store = _event_store(
        "1713870000000-0",
        "1713870000001-0",
        "1713870000002-0",
        "1713870000003-0",
    )

    with (
        _patch_execution_dependencies(service, graph),
        patch(
            "chat.runner.core.publish_user_event", new=AsyncMock()
        ) as publish_user_event,
    ):
        await runner.execute_chat_run(
            session_factory=_session_factory(),
            runner_id="backend-1",
            run_id="run_123",
            event_store=event_store,
        )

    assert [
        awaited.kwargs["event"] for awaited in event_store.append_event.await_args_list
    ] == ["status", "messages", "values", "done"]
    service.touch_last_event.assert_any_await("run_123", event_id="1713870000000-0")
    service.touch_last_event.assert_any_await("run_123", event_id="1713870000001-0")
    service.touch_last_event.assert_any_await("run_123", event_id="1713870000002-0")
    service.mark_completed.assert_awaited_once_with(
        "run_123",
        last_event_id="1713870000003-0",
    )
    publish_user_event.assert_awaited_once()
    assert publish_user_event.await_args.kwargs["user_sub"] == "sub-testuser"
    published = publish_user_event.await_args.kwargs["event"]
    assert published.kind == "chat.run.completed"
    assert published.status == "COMPLETED"
    assert published.resource_id == "thread-1"
    assert "run_123" not in runner._active_run_tasks


@pytest.mark.asyncio
async def test_execute_chat_run_marks_failed_and_appends_error_event_on_exception():
    service = _service()
    event_store = _event_store("1713870000009-0")
    graph = _Graph()

    with (
        _patch_execution_dependencies(
            service,
            graph,
            prepare_side_effect=RuntimeError("model exploded"),
        ),
        patch(
            "chat.runner.core.publish_user_event", new=AsyncMock()
        ) as publish_user_event,
    ):
        await runner.execute_chat_run(
            session_factory=_session_factory(),
            runner_id="backend-1",
            run_id="run_123",
            event_store=event_store,
        )

    event_store.append_event.assert_awaited_once()
    assert event_store.append_event.await_args.kwargs["event"] == "error"
    service.mark_failed.assert_awaited_once_with(
        "run_123",
        error_message="model exploded",
        last_event_id="1713870000009-0",
    )
    publish_user_event.assert_awaited_once()
    assert publish_user_event.await_args.kwargs["user_sub"] == "sub-testuser"
    published = publish_user_event.await_args.kwargs["event"]
    assert published.kind == "chat.run.failed"
    assert published.status == "FAILED"
    assert published.resource_id == "thread-1"
    assert "run_123" not in runner._active_run_tasks


@pytest.mark.asyncio
async def test_execute_chat_run_marks_cancelled_on_task_cancellation():
    service = _service()
    graph = _Graph(exc=asyncio.CancelledError())
    event_store = _event_store("1713870000000-0")

    with _patch_execution_dependencies(service, graph):
        with pytest.raises(asyncio.CancelledError):
            await runner.execute_chat_run(
                session_factory=_session_factory(),
                runner_id="backend-1",
                run_id="run_123",
                event_store=event_store,
            )

    service.mark_cancelled.assert_awaited_once_with(
        "run_123",
        error_message="Chat runner was cancelled.",
    )
    assert "run_123" not in runner._active_run_tasks


@pytest.mark.asyncio
async def test_execute_chat_run_research_mode_appends_report_before_done():
    service = _service(payload=_research_payload())
    graph = _Graph(
        parts=[
            {
                "plan_research": {
                    "title": "Grounded retention report",
                    "outline": ["Findings"],
                }
            },
            {
                "retrieve_evidence": {
                    "sources": [
                        {
                            "file_path": "docs/report.pdf",
                            "title": "Retention Report",
                            "page_numbers": [4],
                            "doc_refs": ["ref-1"],
                            "citation_index": 1,
                            "quote": "Retention improved after the program.",
                        }
                    ]
                }
            },
            {
                "draft_report": {
                    "sections": [
                        {
                            "heading": "Findings",
                            "body": "Retention improved after the program [1].",
                        }
                    ]
                }
            },
            {
                "verify_report": {
                    "images": [],
                    "verification_issues": [],
                    "content_markdown": "# Grounded retention report\n\n## Findings\n\nRetention improved after the program [1].",
                }
            },
        ]
    )
    report_row = SimpleNamespace(
        id="report_123",
        content_markdown="# Grounded retention report\n\n## Findings\n\nRetention improved after the program [1].",
        sources_json=[
            {
                "file_path": "docs/report.pdf",
                "title": "Retention Report",
                "page_numbers": [4],
                "doc_refs": ["ref-1"],
                "images": [],
                "citation_index": 1,
                "quote": "Retention improved after the program.",
            }
        ],
    )
    report_service = SimpleNamespace(
        mark_running=AsyncMock(return_value=report_row),
        mark_completed=AsyncMock(return_value=report_row),
        mark_failed=AsyncMock(),
        mark_cancelled=AsyncMock(),
        to_message_metadata=lambda *args, **kwargs: {
            "kind": "research_report",
            "report_id": "report_123",
            "title": "Grounded retention report",
            "sections": [
                {
                    "heading": "Findings",
                    "body": "Retention improved after the program [1].",
                }
            ],
        },
    )
    conversation_service = SimpleNamespace(append_assistant_message=AsyncMock())
    order: list[str] = []
    event_count = 0

    async def append_event(**kwargs):
        nonlocal event_count
        event_count += 1
        order.append(f"event:{kwargs['event']}")
        return _event_id(f"{event_count}-0")

    async def mark_completed_report(*args, **kwargs):
        order.append("report:mark_completed")
        return report_row

    async def append_report_message(*args, **kwargs):
        order.append("conversation:append_assistant_message")
        return None

    report_service.mark_completed.side_effect = mark_completed_report
    conversation_service.append_assistant_message.side_effect = append_report_message
    event_store = SimpleNamespace(append_event=AsyncMock(side_effect=append_event))

    with (
        patch("chat.runner.core.ChatRunService", return_value=service),
        patch("chat.runner.core.get_settings", return_value=_settings()),
        patch(
            "chat.runner.core.AiSettingsService",
            return_value=SimpleNamespace(
                get_effective_settings=AsyncMock(return_value=None)
            ),
        ),
        patch(
            "chat.runner.core.build_request_scoped_research_graph", return_value=graph
        ),
        patch("chat.runner.core.ResearchReportService", return_value=report_service),
        patch(
            "chat.runner.core.ConversationService", return_value=conversation_service
        ),
        patch(
            "chat.runner.core.publish_user_event", new=AsyncMock()
        ) as publish_user_event,
    ):
        await runner.execute_chat_run(
            session_factory=_session_factory(),
            runner_id="backend-1",
            run_id="run_123",
            event_store=event_store,
        )

    assert [
        awaited.kwargs["event"] for awaited in event_store.append_event.await_args_list
    ] == ["status", "progress", "progress", "progress", "progress", "done"]
    assert order.index("conversation:append_assistant_message") < order.index(
        "event:done"
    )
    report_service.mark_running.assert_awaited_once_with("report_123")
    report_service.mark_completed.assert_awaited_once_with(
        "report_123",
        title="Grounded retention report",
        outline=["Findings"],
        sections=[
            {
                "heading": "Findings",
                "body": "Retention improved after the program [1].",
            }
        ],
        sources=[
            {
                "file_path": "docs/report.pdf",
                "title": "Retention Report",
                "page_numbers": [4],
                "doc_refs": ["ref-1"],
                "citation_index": 1,
                "quote": "Retention improved after the program.",
            }
        ],
        images=[],
        verification_issues=[],
        content_markdown="# Grounded retention report\n\n## Findings\n\nRetention improved after the program [1].",
    )
    conversation_service.append_assistant_message.assert_awaited_once()
    appended_message = conversation_service.append_assistant_message.await_args.args[1]
    assert appended_message.id == "research-report:report_123"
    assert appended_message.content.startswith("# Grounded retention report")
    assert appended_message.additional_kwargs["metadata"]["kind"] == "research_report"
    assert appended_message.additional_kwargs["sources"] == list(
        report_row.sources_json
    )
    service.mark_completed.assert_awaited_once_with("run_123", last_event_id="6-0")
    publish_user_event.assert_awaited_once()
    published = publish_user_event.await_args.kwargs["event"]
    assert published.kind == "research.run.completed"
    assert published.metadata["report_id"] == "report_123"
    assert "run_123" not in runner._active_run_tasks


@pytest.mark.asyncio
async def test_execute_chat_run_stops_without_done_when_run_was_cancelled():
    service = _service()
    service.get_run_status.return_value = ChatRunStatus.CANCELLED
    graph = _Graph(parts=[{"type": "messages", "data": {"delta": "hello"}}])
    event_store = _event_store("1713870000000-0")

    with _patch_execution_dependencies(service, graph):
        await runner.execute_chat_run(
            session_factory=_session_factory(),
            runner_id="backend-1",
            run_id="run_123",
            event_store=event_store,
        )

    event_store.append_event.assert_awaited_once()
    assert event_store.append_event.await_args.kwargs["event"] == "status"
    service.mark_completed.assert_not_awaited()
    service.mark_failed.assert_not_awaited()
    assert "run_123" not in runner._active_run_tasks


@pytest.mark.asyncio
async def test_process_next_chat_run_returns_false_without_valkey_client():
    with (
        patch("chat.runner.core.get_valkey_client", return_value=None),
        patch("chat.runner.core.init_valkey_client", new=AsyncMock(return_value=None)),
    ):
        processed = await runner.process_next_chat_run(
            session_factory=_session_factory(),
            runner_id="backend-1",
        )

    assert processed is False


@pytest.mark.asyncio
async def test_process_next_chat_run_returns_false_when_no_run_is_claimed():
    service = SimpleNamespace(claim_next_pending_run=AsyncMock(return_value=None))

    with (
        patch("chat.runner.core.get_valkey_client", return_value=object()),
        patch("chat.runner.core.ChatRunService", return_value=service),
        patch("chat.runner.core.get_settings", return_value=_settings()),
    ):
        processed = await runner.process_next_chat_run(
            session_factory=_session_factory(),
            runner_id="backend-1",
        )

    assert processed is False
    service.claim_next_pending_run.assert_awaited_once_with(
        claimed_by="backend-1",
        claim_timeout_seconds=300,
    )


@pytest.mark.asyncio
async def test_process_next_chat_run_executes_claimed_run():
    service = SimpleNamespace(
        claim_next_pending_run=AsyncMock(return_value=SimpleNamespace(id="run_123"))
    )
    execute_chat_run = AsyncMock(return_value=None)

    with (
        patch("chat.runner.core.get_valkey_client", return_value=object()),
        patch("chat.runner.core.ChatRunService", return_value=service),
        patch("chat.runner.core.get_settings", return_value=_settings()),
        patch("chat.runner.core.execute_chat_run", new=execute_chat_run),
    ):
        processed = await runner.process_next_chat_run(
            session_factory=_session_factory(),
            runner_id="backend-1",
        )

    assert processed is True
    execute_chat_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_next_chat_run_returns_true_when_execution_task_is_cancelled():
    service = SimpleNamespace(
        claim_next_pending_run=AsyncMock(return_value=SimpleNamespace(id="run_123"))
    )
    execute_chat_run = AsyncMock(side_effect=asyncio.CancelledError)

    with (
        patch("chat.runner.core.get_valkey_client", return_value=object()),
        patch("chat.runner.core.ChatRunService", return_value=service),
        patch("chat.runner.core.get_settings", return_value=_settings()),
        patch("chat.runner.core.execute_chat_run", new=execute_chat_run),
    ):
        processed = await runner.process_next_chat_run(
            session_factory=_session_factory(),
            runner_id="backend-1",
        )

    assert processed is True


@pytest.mark.asyncio
async def test_heartbeat_loop_stops_when_service_reports_not_alive():
    service = SimpleNamespace(heartbeat_run=AsyncMock(return_value=False))

    with (
        patch("chat.runner.core.asyncio.sleep", new=AsyncMock(return_value=None)),
        patch("chat.runner.core.ChatRunService", return_value=service),
    ):
        await runner._heartbeat_chat_run_loop(
            session_factory=_session_factory(),
            run_id="run_123",
            runner_id="backend-1",
            interval_seconds=1,
        )

    service.heartbeat_run.assert_awaited_once_with(
        "run_123",
        claimed_by="backend-1",
    )
