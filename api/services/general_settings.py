"""Load and persist app-wide general settings stored as one AppSetting row."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings as get_app_config
from models.general_settings import GeneralSettings, GeneralSettingsUpdate
from models.sqlalchemy_models import AppSetting

GENERAL_SETTINGS_KEY = "general_settings"


def _normalize_base_url(value: str | None) -> str | None:
    """Trim whitespace and a trailing slash; empty becomes ``None``."""
    if not value:
        return None
    cleaned = value.strip().rstrip("/")
    return cleaned or None


def _config_public_base_url() -> str | None:
    """The public base URL from server config (PUBLIC_BASE_URL env / config.yaml)."""
    return _normalize_base_url(getattr(get_app_config(), "PUBLIC_BASE_URL", ""))


class GeneralSettingsService:
    """Read/write general settings persisted in the ``app_settings`` table.

    Precedence for the effective public base URL: admin override (DB) →
    server config → ``None`` (caller falls back to the request origin).
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _load_row(self) -> AppSetting | None:
        result = await self.db.execute(
            select(AppSetting).where(AppSetting.key == GENERAL_SETTINGS_KEY)
        )
        return result.scalar_one_or_none()

    async def _load_override(self) -> str | None:
        row = await self._load_row()
        data = row.value_json if row and isinstance(row.value_json, dict) else {}
        return _normalize_base_url(data.get("public_base_url"))

    async def get_settings(self) -> GeneralSettings:
        return GeneralSettings(
            public_base_url=await self._load_override(),
            config_public_base_url=_config_public_base_url(),
        )

    async def get_public_base_url(self) -> str | None:
        """Effective value: admin override, else server config, else ``None``."""
        return (await self._load_override()) or _config_public_base_url()

    async def update_settings(
        self,
        payload: GeneralSettingsUpdate,
        *,
        updated_by: str | None = None,
    ) -> GeneralSettings:
        normalized = _normalize_base_url(payload.public_base_url)
        value_json = {"public_base_url": normalized}
        row = await self._load_row()
        if row is None:
            self.db.add(
                AppSetting(
                    key=GENERAL_SETTINGS_KEY,
                    value_json=value_json,
                    updated_by=updated_by,
                )
            )
        else:
            row.value_json = value_json
            row.updated_by = updated_by
        await self.db.commit()
        return GeneralSettings(
            public_base_url=normalized,
            config_public_base_url=_config_public_base_url(),
        )
