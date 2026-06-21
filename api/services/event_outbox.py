"""Durable outbox for post-commit side effects."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from chat.time import iso_now
from models.sqlalchemy_models import EventOutbox, utc_now
from models.user import UserEventRecord
from services.user import UserEventStore
from services.valkey import init_valkey_client, is_valkey_configured

logger = logging.getLogger(__name__)


class EventOutboxService:
    """Create and dispatch durable backend side effects."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def enqueue_user_event(
        self,
        *,
        user_sub: str | None,
        kind: str,
        resource_type: str,
        resource_id: str,
        status: str,
        metadata: dict[str, Any],
    ) -> None:
        self.db.add(
            EventOutbox(
                id=uuid.uuid4().hex,
                event_type="user_event",
                aggregate_type=resource_type,
                aggregate_id=resource_id,
                user_sub=user_sub,
                payload_json={
                    "kind": kind,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "status": status,
                    "metadata": metadata,
                    "created_at": iso_now(),
                },
                status="pending",
            )
        )

    async def dispatch_pending(self, *, limit: int = 25) -> int:
        now = utc_now()
        rows = (
            (
                await self.db.execute(
                    select(EventOutbox)
                    .where(
                        EventOutbox.status == "pending",
                        or_(
                            EventOutbox.next_attempt_at.is_(None),
                            EventOutbox.next_attempt_at <= now,
                        ),
                    )
                    .order_by(EventOutbox.created_at)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        processed = 0
        for row in rows:
            try:
                await self._dispatch(row)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logger.exception("Failed to dispatch outbox event %s", row.id)
                row.attempts = (row.attempts or 0) + 1
                row.last_error = str(exc)
                row.next_attempt_at = now + timedelta(
                    seconds=min(300, 2 ** min(row.attempts, 8))
                )
            else:
                row.status = "processed"
                row.processed_at = utc_now()
                row.last_error = None
                processed += 1
            row.updated_at = utc_now()
        if rows:
            await self.db.commit()
        return processed

    async def _dispatch(self, row: EventOutbox) -> None:
        if row.event_type == "user_event":
            payload = row.payload_json or {}
            if not row.user_sub or not is_valkey_configured():
                return
            client = await init_valkey_client()
            if client is None:
                raise RuntimeError("Valkey user events are configured but unavailable")
            await UserEventStore(client).append_event(
                user_sub=row.user_sub,
                event=UserEventRecord.model_validate(payload),
            )
            return
        raise ValueError(f"Unsupported outbox event type: {row.event_type}")
