"""Tests for Valkey-backed chat run event storage."""

import json
from unittest.mock import AsyncMock

from langchain_core.messages import HumanMessage
import pytest
from pydantic import ValidationError

from chat.run.events import ChatRunEventStore


@pytest.mark.asyncio
async def test_append_event_serializes_payload_and_sets_expiry():
    client = AsyncMock()
    client.xadd.return_value = "1713870000000-0"
    store = ChatRunEventStore(client, ttl_seconds=60)

    event = await store.append_event(
        run_id="run_123",
        conversation_id="thread-1",
        event="messages",
        payload={"delta": "hello"},
        created_at="2026-04-23T10:00:00Z",
    )

    assert event.event_id == "1713870000000-0"
    xadd_args = client.xadd.await_args.args
    assert xadd_args[0] == "chat:run:run_123:events"
    assert xadd_args[1]["event"] == "messages"
    assert xadd_args[1]["conversation_id"] == "thread-1"
    assert xadd_args[1]["created_at"] == "2026-04-23T10:00:00Z"
    client.expire.assert_awaited_once_with("chat:run:run_123:events", 60)


@pytest.mark.asyncio
async def test_append_event_serializes_langchain_messages_in_values_payload():
    client = AsyncMock()
    client.xadd.return_value = "1713870000000-0"
    store = ChatRunEventStore(client, ttl_seconds=60)

    event = await store.append_event(
        run_id="run_123",
        conversation_id="thread-1",
        event="values",
        payload={
            "messages": [HumanMessage(content="hello", id="human-1")],
            "updated_at": "2026-04-23T10:00:00Z",
        },
    )

    xadd_args = client.xadd.await_args.args
    assert event.payload["messages"][0].content == "hello"
    assert json.loads(xadd_args[1]["payload"]) == {
        "messages": [
            {
                "content": "hello",
                "additional_kwargs": {},
                "response_metadata": {},
                "type": "human",
                "name": None,
                "id": "human-1",
            }
        ],
        "updated_at": "2026-04-23T10:00:00Z",
    }


@pytest.mark.asyncio
async def test_append_event_skips_expiry_when_ttl_is_non_positive():
    client = AsyncMock()
    client.xadd.return_value = "1713870000000-0"
    store = ChatRunEventStore(client, ttl_seconds=0)

    await store.append_event(
        run_id="run_123",
        conversation_id="thread-1",
        event="messages",
        payload={"delta": "hello"},
    )

    client.expire.assert_not_awaited()


@pytest.mark.asyncio
async def test_replay_events_decodes_stored_rows():
    client = AsyncMock()
    client.xrange.return_value = [
        (
            "1713870000000-0",
            {
                "event": "messages",
                "payload": '{"delta":"hello"}',
                "conversation_id": "thread-1",
                "created_at": "2026-04-23T10:00:00Z",
            },
        )
    ]
    store = ChatRunEventStore(client, ttl_seconds=60)

    events = await store.replay_events(run_id="run_123", after_id=None)

    assert len(events) == 1
    assert events[0].event == "messages"
    assert events[0].payload == {"delta": "hello"}
    assert events[0].event_id == "1713870000000-0"


@pytest.mark.asyncio
async def test_replay_events_decodes_byte_fields():
    client = AsyncMock()
    client.xrange.return_value = [
        (
            b"1713870000000-0",
            {
                b"event": b"messages",
                b"payload": b'{"delta":"hello"}',
                b"conversation_id": b"thread-1",
                b"created_at": b"2026-04-23T10:00:00Z",
            },
        )
    ]
    store = ChatRunEventStore(client, ttl_seconds=60)

    events = await store.replay_events(run_id="run_123", after_id=None)

    assert len(events) == 1
    assert events[0].event == "messages"
    assert events[0].payload == {"delta": "hello"}
    assert events[0].event_id == "1713870000000-0"
    assert events[0].created_at == "2026-04-23T10:00:00Z"


@pytest.mark.asyncio
async def test_replay_events_passes_explicit_limit():
    client = AsyncMock()
    client.xrange.return_value = []
    store = ChatRunEventStore(client, ttl_seconds=60)

    await store.replay_events(run_id="run_123", after_id=None, limit=10)

    client.xrange.assert_awaited_once()
    assert client.xrange.await_args.kwargs["count"] == 10


@pytest.mark.asyncio
async def test_replay_events_uses_exclusive_after_id():
    client = AsyncMock()
    client.xrange.return_value = []
    store = ChatRunEventStore(client, ttl_seconds=60)

    await store.replay_events(run_id="run_123", after_id="1713870000000-0")

    client.xrange.assert_awaited_once()
    assert client.xrange.await_args.kwargs["min"] == "(1713870000000-0"


@pytest.mark.asyncio
async def test_replay_events_rejects_invalid_event_names():
    client = AsyncMock()
    client.xrange.return_value = [
        (
            "1713870000000-0",
            {
                "event": "not-supported",
                "payload": "{}",
                "conversation_id": "thread-1",
            },
        )
    ]
    store = ChatRunEventStore(client, ttl_seconds=60)

    with pytest.raises(ValidationError):
        await store.replay_events(run_id="run_123", after_id=None)


def test_deserialize_payload_returns_non_string_payload_unchanged():
    payload = {"already": "decoded"}

    decoded = ChatRunEventStore._deserialize_payload(payload)

    assert decoded is payload


def test_normalized_fields_decodes_bytes_keys_and_values():
    assert ChatRunEventStore._normalized_fields({b"event": b"done"}) == {
        "event": "done"
    }


@pytest.mark.asyncio
async def test_read_next_events_decodes_xread_batches():
    client = AsyncMock()
    client.xread.return_value = [
        (
            "chat:run:run_123:events",
            [
                (
                    "1713870000001-0",
                    {
                        "event": "done",
                        "payload": '{"status":"COMPLETED"}',
                        "conversation_id": "thread-1",
                    },
                )
            ],
        )
    ]
    store = ChatRunEventStore(client, ttl_seconds=60)

    events = await store.read_next_events(run_id="run_123", after_id="1713870000000-0")

    assert len(events) == 1
    assert events[0].event == "done"
    assert events[0].payload == {"status": "COMPLETED"}
    assert events[0].event_id == "1713870000001-0"


@pytest.mark.asyncio
async def test_read_next_events_returns_empty_list_when_xread_empty():
    client = AsyncMock()
    client.xread.return_value = []
    store = ChatRunEventStore(client, ttl_seconds=60)

    events = await store.read_next_events(
        run_id="run_123",
        after_id="1713870000000-0",
    )

    assert events == []
