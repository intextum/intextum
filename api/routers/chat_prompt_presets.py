"""Public prompt preset endpoints for chat and deep research."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_user
from database import get_db
from models.chat.prompt_presets import PromptPresetListResponse
from models.user import User
from services.chat_prompt_presets import ChatPromptPresetService

router = APIRouter()


@router.get("/prompt-presets", response_model=PromptPresetListResponse)
async def get_chat_prompt_presets(
    _user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> PromptPresetListResponse:
    """Return enabled prompt presets for the authenticated chat UI."""
    return await ChatPromptPresetService(db).get_presets(include_disabled=False)
