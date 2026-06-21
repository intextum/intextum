"""Admin general (app-wide) settings routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_admin
from database import get_db
from models.general_settings import GeneralSettings, GeneralSettingsUpdate
from models.user import User
from services.general_settings import GeneralSettingsService

router = APIRouter()


@router.get("/general-settings", response_model=GeneralSettings)
async def get_general_settings(
    _user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> GeneralSettings:
    """Return app-wide settings (admin)."""
    return await GeneralSettingsService(db).get_settings()


@router.put("/general-settings", response_model=GeneralSettings)
async def update_general_settings(
    body: GeneralSettingsUpdate,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> GeneralSettings:
    """Update app-wide settings (admin)."""
    return await GeneralSettingsService(db).update_settings(
        body, updated_by=user.username
    )
