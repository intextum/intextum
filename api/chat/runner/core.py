"""Background execution helpers for resumable chat runs."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress

from chat.manager import ChatThreadManager
from .events import (
    append_and_touch_event,
    append_done_event,
    append_error_event,
    append_progress_event,
    append_status_event,
)
from .support import (
    build_chat_user_event,
    build_research_user_event,
    normalize_research_final_state,
    payload_user,
    research_prompt,
)
from chat.run.events import ChatRunEventStore
from chat.run.service import ChatRunService
from chat.session import parse_chat_stream_part, prepare_chat_stream_run
from chat.store import thread_config
from chat.time import iso_now
from chat.transport import ChatStreamServiceRequest
from config import get_settings
from models.enums import ChatRunStatus, ConversationRunMode, ResearchRunStatus
from research.graph import build_request_scoped_research_graph
from research.messages import build_research_report_message
from rls import chat_runner_context, set_rls_context
from services.ai_settings import AiSettingsService
from services.conversation import ConversationService
from services.research_reports import ResearchReportService
from services.user import publish_user_event
from services.valkey import get_valkey_client, init_valkey_client

logger = logging.getLogger(__name__)
_active_run_tasks: dict[str, asyncio.Task] = {}


async def _heartbeat_chat_run_loop(
    *,
    session_factory: Callable,
    run_id: str,
    runner_id: str,
    interval_seconds: int,
) -> None:
    """Keep a running chat claim fresh while generation is in flight."""
    if interval_seconds <= 0:
        return

    while True:
        await asyncio.sleep(interval_seconds)
        try:
            async with session_factory() as db:
                alive = await ChatRunService(db).heartbeat_run(
                    run_id,
                    claimed_by=runner_id,
                )
            if not alive:
                return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning("Chat run heartbeat failed for %s: %s", run_id, exc)


async def _run_was_cancelled(service: ChatRunService, run_id: str) -> bool:
    return (await service.get_run_status(run_id)) == ChatRunStatus.CANCELLED


def request_chat_run_cancellation(run_id: str) -> bool:
    """Cancel an in-process chat run task when this backend owns it."""
    task = _active_run_tasks.get(run_id)
    if task is None or task.done():
        return False

    task.cancel()
    return True


async def _execute_chat_mode(
    *,
    db,
    service: ChatRunService,
    payload,
    runner_id: str,
    run_id: str,
    event_store: ChatRunEventStore,
) -> None:
    user = payload_user(payload)
    ai_settings = await AiSettingsService(db).get_effective_settings()
    stream_request = ChatStreamServiceRequest(
        conversation_id=payload.conversation_id,
        messages=payload.messages,
        context_file_paths=payload.context_file_paths,
        mode=payload.mode,
    )
    thread_manager = ChatThreadManager(
        db=db,
        user=user,
        context_file_paths=stream_request.context_file_paths,
        ai_settings=ai_settings,
    )
    prepared_run = await prepare_chat_stream_run(
        thread_manager=thread_manager,
        stream_request=stream_request,
    )

    await append_status_event(
        service=service,
        event_store=event_store,
        run_id=run_id,
        conversation_id=payload.conversation_id,
        runner_id=runner_id,
        created_at=iso_now(),
    )

    async for part in prepared_run.thread_manager.graph.astream(
        prepared_run.graph_input,
        config=thread_config(prepared_run.conversation_id),
        stream_mode=["messages", "values"],
        version="v2",
    ):
        event = parse_chat_stream_part(part)
        if event is None:
            continue

        if await _run_was_cancelled(service, run_id):
            return

        await append_and_touch_event(
            service=service,
            event_store=event_store,
            run_id=run_id,
            conversation_id=payload.conversation_id,
            event=event.event,
            payload=event.data,
        )

    if await _run_was_cancelled(service, run_id):
        return

    done_event_id = await append_done_event(
        service=service,
        event_store=event_store,
        run_id=run_id,
        conversation_id=payload.conversation_id,
        payload={"status": "COMPLETED"},
        created_at=iso_now(),
    )
    await service.mark_completed(run_id, last_event_id=done_event_id)
    await publish_user_event(
        user_sub=payload.user.sub,
        event=build_chat_user_event(
            payload=payload,
            kind="chat.run.completed",
            status=ChatRunStatus.COMPLETED.value,
        ),
    )


async def _execute_research_mode(
    *,
    db,
    service: ChatRunService,
    payload,
    runner_id: str,
    run_id: str,
    event_store: ChatRunEventStore,
) -> None:
    if not payload.research_report_id:
        raise ValueError("Research run is missing its report id")

    user = payload_user(payload)
    prompt = research_prompt(payload)
    ai_settings = await AiSettingsService(db).get_effective_settings()
    report_service = ResearchReportService(db)
    graph = build_request_scoped_research_graph(
        db=db,
        user=user,
        context_file_paths=payload.context_file_paths,
        ai_settings=ai_settings,
    )
    initial_state = {
        "prompt": prompt,
        "context_file_paths": payload.context_file_paths,
    }

    await report_service.mark_running(payload.research_report_id)
    await append_status_event(
        service=service,
        event_store=event_store,
        run_id=run_id,
        conversation_id=payload.conversation_id,
        runner_id=runner_id,
        created_at=iso_now(),
    )

    final_state = dict(initial_state)
    async for update in graph.astream(initial_state, stream_mode="updates"):
        if not isinstance(update, dict):
            continue
        for node_name, node_update in update.items():
            if isinstance(node_update, dict):
                final_state.update(node_update)
            if await _run_was_cancelled(service, run_id):
                return
            await append_progress_event(
                service=service,
                event_store=event_store,
                run_id=run_id,
                conversation_id=payload.conversation_id,
                phase=node_name,
            )

    if await _run_was_cancelled(service, run_id):
        return

    normalized_final_state = normalize_research_final_state(final_state)

    report = await report_service.mark_completed(
        payload.research_report_id,
        title=normalized_final_state["title"],
        outline=normalized_final_state["outline"],
        sections=normalized_final_state["sections"],
        sources=normalized_final_state["sources"],
        images=normalized_final_state["images"],
        verification_issues=normalized_final_state["verification_issues"],
        content_markdown=normalized_final_state["content_markdown"],
    )
    if report is None:
        raise ValueError("Research report disappeared before completion")

    completed_at = iso_now()
    await ConversationService(db=db, user=user).append_assistant_message(
        payload.conversation_id,
        build_research_report_message(
            report_id=report.id,
            content_markdown=report.content_markdown or "",
            sources=list(report.sources_json or []),
            metadata=report_service.to_message_metadata(report, run_id=run_id),
            created_at=completed_at,
        ),
        updated_at=completed_at,
    )
    done_event_id = await append_done_event(
        service=service,
        event_store=event_store,
        run_id=run_id,
        conversation_id=payload.conversation_id,
        payload={
            "status": "COMPLETED",
            "report_id": payload.research_report_id,
        },
        created_at=completed_at,
    )
    await service.mark_completed(run_id, last_event_id=done_event_id)
    await publish_user_event(
        user_sub=payload.user.sub,
        event=build_research_user_event(
            payload=payload,
            kind="research.run.completed",
            status=ResearchRunStatus.COMPLETED.value,
        ),
    )


async def execute_chat_run(
    *,
    session_factory: Callable,
    runner_id: str,
    run_id: str,
    event_store: ChatRunEventStore,
) -> None:
    """Execute one claimed chat run and persist replayable stream events."""
    current_task = asyncio.current_task()
    if current_task is not None:
        _active_run_tasks[run_id] = current_task

    try:
        async with session_factory() as db:
            service = ChatRunService(db)
            payload = await service.get_request_payload(run_id)
            if payload is None:
                logger.warning(
                    "Claimed chat run %s disappeared before execution",
                    run_id,
                )
                return

            await set_rls_context(db, chat_runner_context(payload_user(payload)))

            heartbeat_task = asyncio.create_task(
                _heartbeat_chat_run_loop(
                    session_factory=session_factory,
                    run_id=run_id,
                    runner_id=runner_id,
                    interval_seconds=get_settings().CHAT_RUN_HEARTBEAT_SECONDS,
                )
            )

            try:
                if payload.mode == ConversationRunMode.RESEARCH:
                    await _execute_research_mode(
                        db=db,
                        service=service,
                        payload=payload,
                        runner_id=runner_id,
                        run_id=run_id,
                        event_store=event_store,
                    )
                else:
                    await _execute_chat_mode(
                        db=db,
                        service=service,
                        payload=payload,
                        runner_id=runner_id,
                        run_id=run_id,
                        event_store=event_store,
                    )
            except asyncio.CancelledError:
                logger.info("Chat runner cancelled while processing run %s", run_id)
                with suppress(Exception):
                    await service.mark_cancelled(
                        run_id,
                        error_message="Chat runner was cancelled.",
                    )
                if (
                    payload.mode == ConversationRunMode.RESEARCH
                    and payload.research_report_id
                ):
                    with suppress(Exception):
                        await ResearchReportService(db).mark_cancelled(
                            payload.research_report_id,
                            error_message="Chat runner was cancelled.",
                        )
                raise
            except Exception as exc:  # pylint: disable=broad-exception-caught
                if await _run_was_cancelled(service, run_id):
                    return
                logger.exception("Chat run %s failed: %s", run_id, exc)
                is_research = payload.mode == ConversationRunMode.RESEARCH
                error_message = str(exc) or (
                    "Research generation failed."
                    if is_research
                    else "Chat generation failed."
                )
                last_event_id: str | None = None
                try:
                    last_event_id = await append_error_event(
                        service=service,
                        event_store=event_store,
                        run_id=run_id,
                        conversation_id=payload.conversation_id,
                        error_message=error_message,
                        is_research=is_research,
                        created_at=iso_now(),
                    )
                except Exception:  # pragma: no cover - defensive fallback
                    logger.exception(
                        "Failed to persist error event for chat run %s", run_id
                    )
                await service.mark_failed(
                    run_id,
                    error_message=error_message,
                    last_event_id=last_event_id,
                )
                if is_research and payload.research_report_id:
                    await ResearchReportService(db).mark_failed(
                        payload.research_report_id,
                        error_message=error_message,
                    )
                    await publish_user_event(
                        user_sub=payload.user.sub,
                        event=build_research_user_event(
                            payload=payload,
                            kind="research.run.failed",
                            status=ResearchRunStatus.FAILED.value,
                        ),
                    )
                else:
                    await publish_user_event(
                        user_sub=payload.user.sub,
                        event=build_chat_user_event(
                            payload=payload,
                            kind="chat.run.failed",
                            status=ChatRunStatus.FAILED.value,
                        ),
                    )
            finally:
                heartbeat_task.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat_task
    finally:
        if current_task is not None and _active_run_tasks.get(run_id) is current_task:
            del _active_run_tasks[run_id]


async def process_next_chat_run(
    *,
    session_factory: Callable,
    runner_id: str,
) -> bool:
    """Claim and execute the next pending chat run, if any."""
    client = get_valkey_client()
    if client is None:
        client = await init_valkey_client()
    if client is None:
        return False

    async with session_factory() as db:
        claimed_run = await ChatRunService(db).claim_next_pending_run(
            claimed_by=runner_id,
            claim_timeout_seconds=get_settings().CHAT_RUN_CLAIM_TIMEOUT_SECONDS,
        )

    if claimed_run is None:
        return False

    execution_task = asyncio.create_task(
        execute_chat_run(
            session_factory=session_factory,
            runner_id=runner_id,
            run_id=claimed_run.id,
            event_store=ChatRunEventStore(client),
        )
    )
    try:
        await execution_task
    except asyncio.CancelledError:
        current_task = asyncio.current_task()
        if current_task is not None and current_task.cancelling():
            execution_task.cancel()
            raise
        return True
    return True
