"""Resumable conversation run API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_user
from chat.submissions import build_human_messages, derive_title_from_text
from chat.run.events import ChatRunEventStore
from chat.run.service import ActiveChatRunExistsError, ChatRunService
from chat.runner import request_chat_run_cancellation
from chat.stream import build_streaming_response, encode_sse_event
from chat.time import iso_now
from chat.transport import parse_stream_request
from config import get_settings
from database import get_db
from models.chat.runs import ChatRunRequestPayload, CreateChatRunResponse, ChatRunRecord
from models.enums import ChatRunStatus, ConversationRunMode, ResearchRunStatus
from models.user import UserEventRecord
from models.user import User
from services.conversation import ConversationService
from services.research_reports import ResearchReportService
from services.user import publish_user_event
from services.valkey import init_valkey_client, is_valkey_configured

router = APIRouter(prefix="/runs")
logger = logging.getLogger(__name__)

ACTIVE_CHAT_RUN_STATUSES = {"PENDING", "RUNNING"}


def _require_user_sub(user: User) -> str:
    try:
        return user.require_stable_sub()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication subject missing",
        ) from e


def _user_payload(user: User) -> ChatRunRequestPayload.UserPayload:
    return ChatRunRequestPayload.UserPayload(
        username=user.username,
        sub=user.require_stable_sub(),
        email=user.email,
        groups=list(user.groups),
        is_admin=user.is_admin,
        preferred_username=user.preferred_username,
        uid=user.uid,
        gids=list(user.gids),
    )


def _terminal_status(run: ChatRunRecord) -> bool:
    return run.status not in ACTIVE_CHAT_RUN_STATUSES


def _runs_enabled(mode: ConversationRunMode) -> bool:
    settings = get_settings()
    if not settings.CHAT_RUNNER_ENABLED or not is_valkey_configured():
        return False
    return mode != ConversationRunMode.RESEARCH or settings.RESEARCH_RUNNER_ENABLED


def _disabled_runs_detail(mode: ConversationRunMode) -> str:
    if mode == ConversationRunMode.RESEARCH:
        return "Deep research is not configured"
    return "Resumable chat runs are not configured"


def _submitted_human_messages(payload: ChatRunRequestPayload) -> list[HumanMessage]:
    return build_human_messages(
        payload.messages,
        context_file_paths=payload.context_file_paths,
    )


def _research_prompt(payload: ChatRunRequestPayload) -> str:
    human_messages = _submitted_human_messages(payload)
    if not human_messages:
        raise ValueError("messages must include at least one user message")
    return str(human_messages[0].content)


async def _append_cancelled_event(run: ChatRunRecord) -> str | None:
    if not is_valkey_configured():
        return None

    client = await init_valkey_client()
    if client is None:
        return None

    try:
        event = await ChatRunEventStore(client).append_event(
            run_id=run.id,
            conversation_id=run.conversation_id,
            event="done",
            payload={"status": "CANCELLED"},
            created_at=iso_now(),
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Failed to append cancellation event for %s: %s",
            run.id,
            exc,
            exc_info=True,
        )
        return None

    return event.event_id


async def _publish_cancelled_user_event(user_sub: str, run: ChatRunRecord) -> None:
    if run.mode == ConversationRunMode.RESEARCH:
        await publish_user_event(
            user_sub=user_sub,
            event=UserEventRecord(
                kind="research.run.cancelled",
                resource_type="conversation",
                resource_id=run.conversation_id,
                status=ResearchRunStatus.CANCELLED.value,
                metadata={
                    "conversation_id": run.conversation_id,
                    "report_id": run.research_report_id,
                },
                created_at=iso_now(),
            ),
        )
        return

    await publish_user_event(
        user_sub=user_sub,
        event=UserEventRecord(
            kind="chat.run.cancelled",
            resource_type="conversation",
            resource_id=run.conversation_id,
            status=ChatRunStatus.CANCELLED.value,
            metadata={"conversation_id": run.conversation_id},
            created_at=iso_now(),
        ),
    )


@router.post("", response_model=CreateChatRunResponse)
async def create_conversation_run(
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Create one resumable conversation run from the normalized stream request."""
    parsed = await parse_stream_request(request)
    if not _runs_enabled(parsed.mode):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_disabled_runs_detail(parsed.mode),
        )

    user_sub = _require_user_sub(user)
    conversation_service = ConversationService(db=db, user=user)

    try:
        await conversation_service.ensure_conversation_for_submission(parsed)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    payload = ChatRunRequestPayload(
        conversation_id=parsed.conversation_id,
        mode=parsed.mode,
        user=_user_payload(user),
        messages=parsed.messages,
        context_file_paths=parsed.context_file_paths,
    )
    report_service = ResearchReportService(db)
    report = None
    if parsed.mode == ConversationRunMode.RESEARCH:
        prompt = _research_prompt(payload)
        report = await report_service.create_report(
            conversation_id=parsed.conversation_id,
            user_sub=user_sub,
            prompt=prompt,
            context_file_paths=parsed.context_file_paths,
            title=derive_title_from_text(prompt),
        )
        payload.research_report_id = report.id

    try:
        created = await ChatRunService(db).create_run(
            conversation_id=parsed.conversation_id,
            user_sub=user_sub,
            request_payload=payload.model_dump(mode="json"),
            mode=payload.mode.value,
            research_report_id=payload.research_report_id,
        )
    except ActiveChatRunExistsError as e:
        if report is not None:
            await report_service.delete_report(report.id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conversation already has an active run",
        ) from e

    if parsed.mode == ConversationRunMode.RESEARCH:
        try:
            await conversation_service.persist_submitted_messages(parsed)
        except Exception as exc:
            await ChatRunService(db).mark_failed(
                created.id,
                error_message=str(exc),
            )
            if report is not None:
                await report_service.mark_failed(
                    report.id,
                    error_message=str(exc),
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            ) from exc

    return CreateChatRunResponse(
        run_id=created.id,
        conversation_id=created.conversation_id,
        mode=created.mode,
        research_report_id=created.research_report_id,
        status=created.status,
    )


@router.get("/{run_id}", response_model=ChatRunRecord)
async def get_conversation_run(
    run_id: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Return one owned resumable chat run."""
    user_sub = _require_user_sub(user)
    run = await ChatRunService(db).get_owned_run(run_id, user_sub)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation run not found",
        )
    return run


@router.post("/{run_id}/cancel", response_model=ChatRunRecord)
async def cancel_conversation_run(
    run_id: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel one active owned resumable chat run."""
    user_sub = _require_user_sub(user)
    run_service = ChatRunService(db)
    run = await run_service.get_owned_run(run_id, user_sub)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation run not found",
        )

    if _terminal_status(run):
        return run

    last_event_id = await _append_cancelled_event(run)
    cancelled = await run_service.mark_cancelled(
        run_id,
        error_message="Cancelled by user.",
        last_event_id=last_event_id,
    )
    if run.mode == ConversationRunMode.RESEARCH and run.research_report_id:
        await ResearchReportService(db).mark_cancelled(
            run.research_report_id,
            error_message="Cancelled by user.",
        )
    request_chat_run_cancellation(run_id)
    await _publish_cancelled_user_event(user_sub, cancelled or run)
    return cancelled or run


@router.get("/{run_id}/stream")
async def stream_conversation_run(
    run_id: str,
    request: Request,
    after: str | None = Query(default=None),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Replay and tail persisted run events for one owned conversation run."""
    user_sub = _require_user_sub(user)
    run_service = ChatRunService(db)
    run = await run_service.get_owned_run(run_id, user_sub)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation run not found",
        )

    if not is_valkey_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Resumable chat runs are not configured",
        )

    client = await init_valkey_client()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Resumable chat runs are not configured",
        )

    event_store = ChatRunEventStore(client)
    last_event_id = after or request.headers.get("Last-Event-ID")

    async def iter_run_frames():
        current_event_id = last_event_id
        replayed_done = False
        replay_limit = max(1, get_settings().CHAT_RUN_MAX_REPLAY_EVENTS)

        async def replay_available_events():
            nonlocal current_event_id, replayed_done
            while True:
                replayed_events = await event_store.replay_events(
                    run_id=run_id,
                    after_id=current_event_id,
                    limit=replay_limit,
                )
                if not replayed_events:
                    return

                for event in replayed_events:
                    current_event_id = event.event_id or current_event_id
                    if event.event == "done":
                        replayed_done = True
                    yield encode_sse_event(
                        event.event,
                        event.payload,
                        event_id=event.event_id,
                    )

                if replayed_done or len(replayed_events) < replay_limit:
                    return

        async for frame in replay_available_events():
            yield frame
        if replayed_done:
            return
        if _terminal_status(run):
            return

        while True:
            next_events = await event_store.read_next_events(
                run_id=run_id,
                after_id=current_event_id,
            )
            if not next_events:
                current_run = await run_service.get_owned_run(run_id, user_sub)
                if current_run is None:
                    return
                if _terminal_status(current_run):
                    async for frame in replay_available_events():
                        yield frame
                    return
                continue

            for event in next_events:
                current_event_id = event.event_id
                yield encode_sse_event(
                    event.event,
                    event.payload,
                    event_id=event.event_id,
                )

            if next_events[-1].event == "done":
                return

    return build_streaming_response(iter_run_frames())
