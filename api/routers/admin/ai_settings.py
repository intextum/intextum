"""Admin endpoints for runtime-overridable AI settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_admin
from database import get_db
from models.ai_settings import (
    AiSettingsResponse,
    AiSettingsUpdateRequest,
    ResetAiSettingsRequest,
)
from models.user import User
from services.ai_settings import AI_SETTING_BY_KEY, AiSettingsService

router = APIRouter()


@router.get("/ai-settings", response_model=AiSettingsResponse)
async def get_ai_settings(
    _user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AiSettingsResponse:
    """Return editable AI settings with default/effective values."""
    return await AiSettingsService(db).get_admin_response()


@router.patch("/ai-settings", response_model=AiSettingsResponse)
async def update_ai_settings(
    request: AiSettingsUpdateRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AiSettingsResponse:
    """Persist one or more admin-supplied AI setting overrides."""
    updates = request.model_dump(exclude_none=True)
    return await AiSettingsService(db).update_settings(
        updates,
        updated_by=user.username,
    )


@router.delete("/ai-settings/{setting_key}", response_model=AiSettingsResponse)
async def reset_ai_setting(
    setting_key: str,
    _user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AiSettingsResponse:
    """Reset one AI setting to its deployment default."""
    if setting_key not in AI_SETTING_BY_KEY:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Unknown AI setting")
    return await AiSettingsService(db).reset_settings(keys=[setting_key])


@router.post("/ai-settings/reset", response_model=AiSettingsResponse)
async def reset_ai_settings(
    request: ResetAiSettingsRequest,
    _user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AiSettingsResponse:
    """Reset a subset or all AI settings to their deployment defaults."""
    invalid = [key for key in request.keys or [] if key not in AI_SETTING_BY_KEY]
    if invalid:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail=f"Unknown AI setting(s): {', '.join(sorted(invalid))}",
        )
    return await AiSettingsService(db).reset_settings(keys=request.keys)
