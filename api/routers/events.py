"""User-scoped lifecycle event streaming endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from auth.dependencies import require_user
from chat.stream import build_streaming_response, encode_sse_event
from config import get_settings
from models.user import User, UserEventRecord
from services.user import UserEventStore
from services.valkey import init_valkey_client, is_valkey_configured

router = APIRouter(prefix="/events")


def _require_user_sub(user: User) -> str:
    try:
        return user.require_stable_sub()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication subject missing",
        ) from exc


def _user_event_frame(event: UserEventRecord) -> str:
    return encode_sse_event(
        "user-event",
        event.model_dump(mode="json"),
        event_id=event.event_id,
    )


@router.get("/stream")
async def stream_user_events(
    request: Request,
    after: str | None = Query(default=None),
    user: User = Depends(require_user),
):
    """Replay and tail lifecycle events for the current authenticated user."""
    user_sub = _require_user_sub(user)
    if not is_valkey_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User events are not configured",
        )

    client = await init_valkey_client()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User events are not configured",
        )

    event_store = UserEventStore(client)
    last_event_id = after or request.headers.get("Last-Event-ID")

    async def iter_user_event_frames():
        current_event_id = last_event_id
        replay_limit = max(1, get_settings().USER_EVENT_MAX_REPLAY_EVENTS)

        while True:
            replayed_events = await event_store.replay_events(
                user_sub=user_sub,
                after_id=current_event_id,
                limit=replay_limit,
            )
            if not replayed_events:
                break
            for event in replayed_events:
                current_event_id = event.event_id or current_event_id
                yield _user_event_frame(event)
            if len(replayed_events) < replay_limit:
                break

        while not await request.is_disconnected():
            next_events = await event_store.read_next_events(
                user_sub=user_sub,
                after_id=current_event_id,
            )
            for event in next_events:
                current_event_id = event.event_id or current_event_id
                yield _user_event_frame(event)

    return build_streaming_response(iter_user_event_frames())
