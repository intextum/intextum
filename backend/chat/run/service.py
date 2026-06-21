"""Database service for durable resumable chat run metadata."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.chat.runs import ChatRunRecord, ChatRunRequestPayload
from models.enums import ChatRunStatus, ConversationRunMode
from models.sqlalchemy_models import ChatRun
from services.utils import utcnow

ACTIVE_CHAT_RUN_STATUSES = (
    ChatRunStatus.PENDING.value,
    ChatRunStatus.RUNNING.value,
)


class ActiveChatRunExistsError(RuntimeError):
    """Raised when a conversation already has a pending/running chat run."""


class ChatRunService:
    """CRUD and lifecycle transitions for resumable chat runs."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _to_record(run: ChatRun) -> ChatRunRecord:
        return ChatRunRecord.model_validate(
            {
                "id": run.id,
                "conversation_id": run.conversation_id,
                "user_sub": run.user_sub,
                "mode": run.mode or ConversationRunMode.CHAT.value,
                "research_report_id": run.research_report_id,
                "status": run.status,
                "claimed_by": run.claimed_by,
                "claimed_at": run.claimed_at,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
                "last_event_id": run.last_event_id,
                "error_message": run.error_message,
                "created_at": run.created_at,
                "updated_at": run.updated_at,
            }
        )

    async def _get_active_run_for_conversation(
        self, conversation_id: str
    ) -> ChatRun | None:
        result = await self.db.execute(
            select(ChatRun).where(
                ChatRun.conversation_id == conversation_id,
                ChatRun.status.in_(ACTIVE_CHAT_RUN_STATUSES),
            )
        )
        return result.scalar_one_or_none()

    async def _get_run(self, run_id: str) -> ChatRun | None:
        result = await self.db.execute(select(ChatRun).where(ChatRun.id == run_id))
        return result.scalar_one_or_none()

    def _mark_terminal(
        self,
        run: ChatRun,
        *,
        status: ChatRunStatus,
        now: datetime,
        error_message: str | None = None,
        last_event_id: str | None = None,
    ) -> None:
        run.status = status.value
        run.error_message = error_message
        run.finished_at = now
        run.updated_at = now
        if last_event_id is not None:
            run.last_event_id = last_event_id

    async def has_active_run(self, conversation_id: str) -> bool:
        """Return whether a conversation already has a pending/running run."""
        return await self._get_active_run_for_conversation(conversation_id) is not None

    async def create_run(
        self,
        *,
        conversation_id: str,
        user_sub: str,
        request_payload: dict[str, Any],
        mode: str = ConversationRunMode.CHAT.value,
        research_report_id: str | None = None,
    ) -> ChatRunRecord:
        """Create a new pending chat run, rejecting duplicate active runs."""
        if await self.has_active_run(conversation_id):
            raise ActiveChatRunExistsError(
                f"Conversation {conversation_id} already has an active run"
            )

        now = utcnow()
        run = ChatRun(
            id=f"run_{uuid.uuid4().hex}",
            conversation_id=conversation_id,
            user_sub=user_sub,
            mode=mode,
            research_report_id=research_report_id,
            status=ChatRunStatus.PENDING.value,
            request_json=request_payload,
            created_at=now,
            updated_at=now,
        )
        self.db.add(run)
        await self.db.commit()
        return self._to_record(run)

    async def get_owned_run(self, run_id: str, user_sub: str) -> ChatRunRecord | None:
        """Return a chat run only when it belongs to the supplied user."""
        result = await self.db.execute(
            select(ChatRun).where(ChatRun.id == run_id, ChatRun.user_sub == user_sub)
        )
        run = result.scalar_one_or_none()
        if run is None:
            return None
        return self._to_record(run)

    async def list_active_runs_for_user(self, user_sub: str) -> list[ChatRunRecord]:
        """Return the current user's pending/running runs ordered newest first."""
        result = await self.db.execute(
            select(ChatRun)
            .where(
                ChatRun.user_sub == user_sub,
                ChatRun.status.in_(ACTIVE_CHAT_RUN_STATUSES),
            )
            .order_by(ChatRun.updated_at.desc(), ChatRun.created_at.desc())
        )
        return [self._to_record(run) for run in result.scalars().all()]

    async def get_request_payload(self, run_id: str) -> ChatRunRequestPayload | None:
        """Return the serialized chat request payload for one run."""
        run = await self._get_run(run_id)
        if run is None:
            return None
        return ChatRunRequestPayload.model_validate(run.request_json)

    async def claim_next_pending_run(
        self,
        *,
        claimed_by: str,
        claim_timeout_seconds: int,
    ) -> ChatRunRecord | None:
        """Claim the oldest pending or stale running run for execution."""
        now = utcnow()
        cutoff = now - timedelta(seconds=max(claim_timeout_seconds, 0))
        stale_running_run = and_(
            ChatRun.status == ChatRunStatus.RUNNING.value,
            or_(
                ChatRun.claimed_at.is_(None),
                ChatRun.claimed_at < cutoff,
            ),
        )
        result = await self.db.execute(
            select(ChatRun)
            .where(
                or_(
                    ChatRun.status == ChatRunStatus.PENDING.value,
                    stale_running_run,
                )
            )
            .order_by(ChatRun.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        run = result.scalar_one_or_none()
        if run is None:
            return None

        run.status = ChatRunStatus.RUNNING.value
        run.claimed_by = claimed_by
        run.claimed_at = now
        if run.started_at is None:
            run.started_at = now
        run.updated_at = now
        run.error_message = None
        await self.db.commit()
        return self._to_record(run)

    async def heartbeat_run(self, run_id: str, *, claimed_by: str) -> bool:
        """Refresh claim metadata for a run still owned by this runner."""
        result = await self.db.execute(
            select(ChatRun)
            .where(ChatRun.id == run_id)
            .execution_options(populate_existing=True)
        )
        run = result.scalar_one_or_none()
        if (
            run is None
            or run.status != ChatRunStatus.RUNNING.value
            or run.claimed_by != claimed_by
        ):
            return False

        now = utcnow()
        run.claimed_at = now
        run.updated_at = now
        await self.db.commit()
        return True

    async def get_run_status(self, run_id: str) -> ChatRunStatus | None:
        """Return the current persisted status for one run."""
        result = await self.db.execute(
            select(ChatRun.status)
            .where(ChatRun.id == run_id)
            .execution_options(populate_existing=True)
        )
        status = result.scalar_one_or_none()
        if status is None:
            return None
        return ChatRunStatus(status)

    async def mark_completed(
        self,
        run_id: str,
        *,
        last_event_id: str | None = None,
    ) -> ChatRunRecord | None:
        """Mark a claimed/running run as completed."""
        run = await self._get_run(run_id)
        if run is None:
            return None

        self._mark_terminal(
            run,
            status=ChatRunStatus.COMPLETED,
            now=utcnow(),
            last_event_id=last_event_id,
        )
        await self.db.commit()
        return self._to_record(run)

    async def mark_failed(
        self,
        run_id: str,
        *,
        error_message: str,
        last_event_id: str | None = None,
    ) -> ChatRunRecord | None:
        """Mark a claimed/running run as failed."""
        run = await self._get_run(run_id)
        if run is None:
            return None

        self._mark_terminal(
            run,
            status=ChatRunStatus.FAILED,
            now=utcnow(),
            error_message=error_message,
            last_event_id=last_event_id,
        )
        await self.db.commit()
        return self._to_record(run)

    async def mark_cancelled(
        self,
        run_id: str,
        *,
        error_message: str | None = None,
        last_event_id: str | None = None,
    ) -> ChatRunRecord | None:
        """Mark a run as cancelled."""
        run = await self._get_run(run_id)
        if run is None:
            return None

        if run.status not in ACTIVE_CHAT_RUN_STATUSES:
            return self._to_record(run)

        self._mark_terminal(
            run,
            status=ChatRunStatus.CANCELLED,
            now=utcnow(),
            error_message=error_message,
            last_event_id=last_event_id,
        )
        await self.db.commit()
        return self._to_record(run)

    async def touch_last_event(
        self,
        run_id: str,
        *,
        event_id: str | None = None,
    ) -> ChatRunRecord | None:
        """Persist the most recent emitted event identifier."""
        run = await self._get_run(run_id)
        if run is None:
            return None

        if event_id is not None:
            run.last_event_id = event_id
        run.updated_at = utcnow()
        await self.db.commit()
        return self._to_record(run)
