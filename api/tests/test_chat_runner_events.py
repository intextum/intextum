"""Focused tests for chat runner event helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from chat.runner.events import (
    append_and_touch_event,
    append_done_event,
    append_error_event,
    append_progress_event,
    append_status_event,
)


def _service():
    return SimpleNamespace(touch_last_event=AsyncMock())


def _event_store(event_id: str = "1713870000000-0"):
    return SimpleNamespace(
        append_event=AsyncMock(return_value=SimpleNamespace(event_id=event_id))
    )


@pytest.mark.asyncio
async def test_append_and_touch_event_updates_last_event_pointer():
    service = _service()
    event_store = _event_store("1-0")

    event_id = await append_and_touch_event(
        service=service,
        event_store=event_store,
        run_id="run_123",
        conversation_id="thread-1",
        event="messages",
        payload={"delta": "hello"},
    )

    assert event_id == "1-0"
    event_store.append_event.assert_awaited_once_with(
        run_id="run_123",
        conversation_id="thread-1",
        event="messages",
        payload={"delta": "hello"},
        created_at=None,
    )
    service.touch_last_event.assert_awaited_once_with("run_123", event_id="1-0")


@pytest.mark.asyncio
async def test_append_status_event_persists_running_payload():
    service = _service()
    event_store = _event_store()

    await append_status_event(
        service=service,
        event_store=event_store,
        run_id="run_123",
        conversation_id="thread-1",
        runner_id="backend-1",
    )

    assert event_store.append_event.await_args.kwargs["event"] == "status"
    assert event_store.append_event.await_args.kwargs["payload"] == {
        "status": "RUNNING",
        "runner_id": "backend-1",
    }


@pytest.mark.asyncio
async def test_append_progress_event_uses_research_phase_label():
    service = _service()
    event_store = _event_store()

    await append_progress_event(
        service=service,
        event_store=event_store,
        run_id="run_123",
        conversation_id="thread-1",
        phase="verify_report",
    )

    assert event_store.append_event.await_args.kwargs["event"] == "progress"
    assert event_store.append_event.await_args.kwargs["payload"] == {
        "phase": "verify_report",
        "message": "Validated citations and assembled the final report.",
    }


@pytest.mark.asyncio
async def test_append_done_event_persists_terminal_payload():
    service = _service()
    event_store = _event_store()

    await append_done_event(
        service=service,
        event_store=event_store,
        run_id="run_123",
        conversation_id="thread-1",
        payload={"status": "COMPLETED"},
    )

    assert event_store.append_event.await_args.kwargs["event"] == "done"
    assert event_store.append_event.await_args.kwargs["payload"] == {
        "status": "COMPLETED"
    }


@pytest.mark.asyncio
async def test_append_error_event_uses_mode_specific_name():
    service = _service()
    event_store = _event_store()

    await append_error_event(
        service=service,
        event_store=event_store,
        run_id="run_123",
        conversation_id="thread-1",
        error_message="model exploded",
        is_research=True,
    )

    assert event_store.append_event.await_args.kwargs["event"] == "error"
    assert event_store.append_event.await_args.kwargs["payload"] == {
        "name": "ResearchRunError",
        "message": "model exploded",
    }
