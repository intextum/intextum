"""Tests for generic user event storage and streaming."""

import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from auth.dependencies import require_user
from models.user import User
from models.user import UserEventRecord
from routers.events import router as events_router, stream_user_events
from services.user import UserEventStore, publish_user_event


def _event(*, event_id: str | None = None, **overrides) -> UserEventRecord:
    payload = {
        "kind": "chat.run.completed",
        "resource_type": "conversation",
        "resource_id": "thread-1",
        "status": "COMPLETED",
        "metadata": {"conversation_id": "thread-1"},
        "created_at": "2026-04-23T10:00:00Z",
        "event_id": event_id,
    }
    payload.update(overrides)
    return UserEventRecord.model_validate(payload)


def _event_payload(frame: str):
    for line in frame.splitlines():
        if line.startswith("data: "):
            return json.loads(line.removeprefix("data: "))
    raise AssertionError("SSE frame did not contain a data line")


async def _collect_frames(frame_iter):
    return [frame async for frame in frame_iter]


@pytest.mark.asyncio
async def test_user_event_store_appends_and_replays_events():
    client = AsyncMock()
    client.xadd.return_value = "1713870000000-0"
    client.xrange.return_value = [
        (
            "1713870000000-0",
            {
                "kind": "chat.run.completed",
                "resource_type": "conversation",
                "resource_id": "thread-1",
                "status": "COMPLETED",
                "metadata": '{"conversation_id":"thread-1"}',
                "created_at": "2026-04-23T10:00:00Z",
            },
        )
    ]
    store = UserEventStore(client, ttl_seconds=60)

    saved = await store.append_event(
        user_sub="sub-testuser",
        event=UserEventRecord(
            kind="chat.run.completed",
            resource_type="conversation",
            resource_id="thread-1",
            status="COMPLETED",
            metadata={"conversation_id": "thread-1"},
            created_at="2026-04-23T10:00:00Z",
        ),
    )
    replayed = await store.replay_events(user_sub="sub-testuser")

    assert saved.event_id == "1713870000000-0"
    client.expire.assert_awaited_once_with("user:sub-testuser:events", 60)
    assert replayed == [saved]


@pytest.mark.asyncio
async def test_user_event_store_defaults_invalid_replay_metadata_to_empty_dict():
    client = AsyncMock()
    client.xrange.return_value = [
        (
            "1713870000000-0",
            {
                "kind": "chat.run.completed",
                "resource_type": "conversation",
                "resource_id": "thread-1",
                "status": "COMPLETED",
                "metadata": "{not-json",
                "created_at": "2026-04-23T10:00:00Z",
            },
        )
    ]
    store = UserEventStore(client, ttl_seconds=60)

    replayed = await store.replay_events(user_sub="sub-testuser")

    assert replayed[0].metadata == {}


@pytest.mark.asyncio
async def test_publish_user_event_returns_none_when_events_are_unconfigured():
    with patch("services.user.events.is_valkey_configured", return_value=False):
        result = await publish_user_event(
            user_sub="sub-testuser",
            event=_event(metadata={}),
        )

    assert result is None


@pytest.mark.asyncio
async def test_publish_user_event_returns_none_when_user_sub_is_missing():
    with patch(
        "services.user.events.init_valkey_client",
        new=AsyncMock(return_value=object()),
    ) as init_valkey_client:
        result = await publish_user_event(
            user_sub=None,
            event=_event(),
        )

    assert result is None
    init_valkey_client.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_user_event_returns_none_when_client_init_fails():
    with (
        patch("services.user.events.is_valkey_configured", return_value=True),
        patch(
            "services.user.events.init_valkey_client",
            new=AsyncMock(return_value=None),
        ) as init_valkey_client,
    ):
        result = await publish_user_event(
            user_sub="sub-testuser",
            event=_event(),
        )

    assert result is None
    init_valkey_client.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_user_event_returns_none_when_append_raises(caplog):
    append_event = AsyncMock(side_effect=RuntimeError("valkey unavailable"))
    caplog.set_level(logging.WARNING, logger="services.user.events")

    with (
        patch("services.user.events.is_valkey_configured", return_value=True),
        patch(
            "services.user.events.init_valkey_client",
            new=AsyncMock(return_value=object()),
        ),
        patch("services.user.events.UserEventStore.append_event", new=append_event),
    ):
        result = await publish_user_event(
            user_sub="sub-testuser",
            event=_event(),
        )

    assert result is None
    append_event.assert_awaited_once()
    assert "Failed to publish user event chat.run.completed for sub-testuser" in (
        caplog.text
    )
    assert "RuntimeError: valkey unavailable" in caplog.text


def test_stream_user_events_returns_503_when_events_are_unconfigured():
    app = FastAPI()
    app.include_router(events_router, prefix="/api")
    app.dependency_overrides[require_user] = lambda: User(
        username="testuser",
        sub="sub-testuser",
    )

    with (
        patch("routers.events.is_valkey_configured", return_value=False),
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        response = client.get("/api/events/stream")

    assert response.status_code == 503
    assert response.json()["detail"] == "User events are not configured"


@pytest.mark.asyncio
async def test_stream_user_events_returns_503_when_client_init_fails():
    request = SimpleNamespace(
        headers={},
        is_disconnected=AsyncMock(return_value=True),
    )

    with (
        patch("routers.events.is_valkey_configured", return_value=True),
        patch(
            "routers.events.init_valkey_client",
            new=AsyncMock(return_value=None),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await stream_user_events(
                request=request,
                after=None,
                user=User(username="testuser", sub="sub-testuser"),
            )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "User events are not configured"


@pytest.mark.asyncio
async def test_stream_user_events_replays_events_across_pages():
    request = SimpleNamespace(
        headers={},
        is_disconnected=AsyncMock(return_value=True),
    )
    replay_events = AsyncMock(
        side_effect=[
            [_event(event_id="1713870000001-0", status="RUNNING")],
            [_event(event_id="1713870000002-0", status="COMPLETED")],
            [],
        ]
    )

    with (
        patch("routers.events.is_valkey_configured", return_value=True),
        patch(
            "routers.events.init_valkey_client",
            new=AsyncMock(return_value=object()),
        ),
        patch(
            "routers.events.get_settings",
            return_value=SimpleNamespace(USER_EVENT_MAX_REPLAY_EVENTS=1),
        ),
        patch(
            "routers.events.build_streaming_response",
            side_effect=lambda frame_iter: frame_iter,
        ),
        patch("routers.events.UserEventStore.replay_events", new=replay_events),
        patch(
            "routers.events.UserEventStore.read_next_events",
            new=AsyncMock(return_value=[]),
        ),
    ):
        frame_iter = await stream_user_events(
            request=request,
            after="1713870000000-0",
            user=User(username="testuser", sub="sub-testuser"),
        )
        frames = await _collect_frames(frame_iter)

    assert [frame.splitlines()[0] for frame in frames] == [
        "id: 1713870000001-0",
        "id: 1713870000002-0",
    ]
    assert _event_payload(frames[0])["status"] == "RUNNING"
    assert _event_payload(frames[1])["status"] == "COMPLETED"
    assert replay_events.await_args_list == [
        call(user_sub="sub-testuser", after_id="1713870000000-0", limit=1),
        call(user_sub="sub-testuser", after_id="1713870000001-0", limit=1),
        call(user_sub="sub-testuser", after_id="1713870000002-0", limit=1),
    ]


@pytest.mark.asyncio
async def test_stream_user_events_tails_live_events_from_last_event_id_header():
    request = SimpleNamespace(
        headers={"Last-Event-ID": "1713870000000-0"},
        is_disconnected=AsyncMock(side_effect=[False, True]),
    )
    live_events = [
        _event(
            event_id="1713870000001-0",
            kind="file.process.failed",
            resource_type="file",
            resource_id="file-1",
            status="FAILED",
            metadata={"content_item_id": "file-1"},
        )
    ]
    read_next_events = AsyncMock(return_value=live_events)

    with (
        patch("routers.events.is_valkey_configured", return_value=True),
        patch(
            "routers.events.init_valkey_client",
            new=AsyncMock(return_value=object()),
        ),
        patch(
            "routers.events.build_streaming_response",
            side_effect=lambda frame_iter: frame_iter,
        ),
        patch(
            "routers.events.UserEventStore.replay_events",
            new=AsyncMock(return_value=[]),
        ),
        patch("routers.events.UserEventStore.read_next_events", new=read_next_events),
    ):
        frame_iter = await stream_user_events(
            request=request,
            after=None,
            user=User(username="testuser", sub="sub-testuser"),
        )
        frames = await _collect_frames(frame_iter)

    assert len(frames) == 1
    assert "event: user-event" in frames[0]
    assert _event_payload(frames[0])["kind"] == "file.process.failed"
    read_next_events.assert_awaited_once_with(
        user_sub="sub-testuser",
        after_id="1713870000000-0",
    )
