"""Event persistence helpers for background chat-run execution."""

from __future__ import annotations

from typing import Any

from .support import progress_message


async def append_and_touch_event(
    *,
    service: Any,
    event_store: Any,
    run_id: str,
    conversation_id: str,
    event: str,
    payload: dict[str, Any],
    created_at: str | None = None,
) -> str:
    """Persist one run event and update the run pointer to the new event id."""
    stored_event = await event_store.append_event(
        run_id=run_id,
        conversation_id=conversation_id,
        event=event,
        payload=payload,
        created_at=created_at,
    )
    await service.touch_last_event(run_id, event_id=stored_event.event_id)
    return stored_event.event_id


async def append_status_event(
    *,
    service: Any,
    event_store: Any,
    run_id: str,
    conversation_id: str,
    runner_id: str,
    created_at: str | None = None,
) -> str:
    """Persist the standard RUNNING status event for one claimed run."""
    return await append_and_touch_event(
        service=service,
        event_store=event_store,
        run_id=run_id,
        conversation_id=conversation_id,
        event="status",
        payload={"status": "RUNNING", "runner_id": runner_id},
        created_at=created_at,
    )


async def append_progress_event(
    *,
    service: Any,
    event_store: Any,
    run_id: str,
    conversation_id: str,
    phase: str,
    created_at: str | None = None,
) -> str:
    """Persist one research progress update and advance the last-event pointer."""
    return await append_and_touch_event(
        service=service,
        event_store=event_store,
        run_id=run_id,
        conversation_id=conversation_id,
        event="progress",
        payload={
            "phase": phase,
            "message": progress_message(phase),
        },
        created_at=created_at,
    )


async def append_done_event(
    *,
    service: Any,
    event_store: Any,
    run_id: str,
    conversation_id: str,
    payload: dict[str, Any],
    created_at: str | None = None,
) -> str:
    """Persist the terminal done event and update the run pointer."""
    return await append_and_touch_event(
        service=service,
        event_store=event_store,
        run_id=run_id,
        conversation_id=conversation_id,
        event="done",
        payload=payload,
        created_at=created_at,
    )


async def append_error_event(
    *,
    service: Any,
    event_store: Any,
    run_id: str,
    conversation_id: str,
    error_message: str,
    is_research: bool,
    created_at: str | None = None,
) -> str:
    """Persist the standard terminal error event for one failed run."""
    return await append_and_touch_event(
        service=service,
        event_store=event_store,
        run_id=run_id,
        conversation_id=conversation_id,
        event="error",
        payload={
            "name": "ResearchRunError" if is_research else "ChatRunError",
            "message": error_message,
        },
        created_at=created_at,
    )
