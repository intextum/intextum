"""Persistence helpers for materialized conversation metadata."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.sqlalchemy_models import Conversation
from services.utils import utcnow


class ConversationOwnershipError(RuntimeError):
    """Raised when a conversation id already belongs to a different user."""


def _to_db_datetime(value: str | datetime | None) -> datetime:
    if value is None:
        return utcnow()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


class ConversationRecordService:
    """CRUD helpers for the conversations metadata table."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_conversation(self, conversation_id: str) -> Conversation | None:
        """Return one conversation metadata row by id."""
        result = await self.db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        return result.scalar_one_or_none()

    async def get_owned_conversation(
        self,
        conversation_id: str,
        user_sub: str,
    ) -> Conversation | None:
        """Return one conversation row only when it belongs to the user."""
        result = await self.db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_sub == user_sub,
            )
        )
        return result.scalar_one_or_none()

    async def list_owned_conversations(self, user_sub: str) -> list[Conversation]:
        """Return all materialized conversations for one user."""
        result = await self.db.execute(
            select(Conversation)
            .where(Conversation.user_sub == user_sub)
            .order_by(Conversation.updated_at.desc(), Conversation.created_at.desc())
        )
        return list(result.scalars().all())

    async def upsert_conversation(
        self,
        *,
        conversation_id: str,
        user_sub: str,
        title: str | None,
        created_at: str | datetime | None,
        updated_at: str | datetime | None,
        commit: bool = True,
    ) -> Conversation:
        """Create or refresh one conversation metadata row."""
        record = await self.get_conversation(conversation_id)
        resolved_created_at = _to_db_datetime(created_at)
        resolved_updated_at = _to_db_datetime(updated_at)

        if record is None:
            record = Conversation(
                id=conversation_id,
                user_sub=user_sub,
                title=title,
                created_at=resolved_created_at,
                updated_at=resolved_updated_at,
            )
            self.db.add(record)
        else:
            if record.user_sub != user_sub:
                raise ConversationOwnershipError(
                    f"Conversation {conversation_id} belongs to another user"
                )
            if title is not None:
                record.title = title
            if resolved_created_at < record.created_at:
                record.created_at = resolved_created_at
            record.updated_at = resolved_updated_at

        if commit:
            await self.db.commit()
        return record

    async def update_title(
        self,
        *,
        conversation_id: str,
        user_sub: str,
        title: str | None,
        updated_at: str | datetime | None,
    ) -> Conversation | None:
        """Set one conversation title, allowing it to be cleared."""
        record = await self.get_owned_conversation(conversation_id, user_sub)
        if record is None:
            return None

        record.title = title
        record.updated_at = _to_db_datetime(updated_at)
        await self.db.commit()
        return record

    async def delete_owned_conversation(
        self,
        conversation_id: str,
        user_sub: str,
    ) -> bool:
        """Delete one owned conversation metadata row."""
        record = await self.get_owned_conversation(conversation_id, user_sub)
        if record is None:
            return False

        await self.db.delete(record)
        await self.db.commit()
        return True
