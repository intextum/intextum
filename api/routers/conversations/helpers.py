"""Helper functions for conversations."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_user
from database import get_db
from models.user import User
from services.conversation import ConversationService


def get_conversation_service(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_user),
) -> ConversationService:
    """Get the conversation service."""
    return ConversationService(db=db, user=user)
