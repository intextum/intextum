"""Admin endpoints for configurable chat prompt presets."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_admin
from database import get_db
from models.chat.prompt_presets import (
    PromptPresetListResponse,
    PromptPresetUpdateRequest,
)
from models.user import User
from services.chat_prompt_presets import ChatPromptPresetService

router = APIRouter(prefix="/admin/chat-prompt-presets")


@router.get("", response_model=PromptPresetListResponse)
async def get_admin_chat_prompt_presets(
    _user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> PromptPresetListResponse:
    """Return all prompt presets for admin editing."""
    return await ChatPromptPresetService(db).get_presets(include_disabled=True)


@router.put("", response_model=PromptPresetListResponse)
async def replace_admin_chat_prompt_presets(
    request: PromptPresetUpdateRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> PromptPresetListResponse:
    """Replace all admin-managed prompt presets."""
    try:
        return await ChatPromptPresetService(db).replace_presets(
            request.presets,
            updated_by=user.username,
        )
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reset", response_model=PromptPresetListResponse)
async def reset_admin_chat_prompt_presets(
    _user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> PromptPresetListResponse:
    """Reset prompt presets to built-in defaults."""
    return await ChatPromptPresetService(db).reset_presets()
