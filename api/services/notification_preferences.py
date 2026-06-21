"""Service layer for per-user notification preferences."""

from __future__ import annotations

from models.notification_preferences import NotificationPreferences
from models.sqlalchemy_models import UserNotificationPreference
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class NotificationPreferencesService:
    """Load and persist notification presentation preferences for one user."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def defaults() -> NotificationPreferences:
        """Return the application default notification preferences."""
        return NotificationPreferences()

    async def _row_for_user(self, user_sub: str) -> UserNotificationPreference | None:
        result = await self.db.execute(
            select(UserNotificationPreference).where(
                UserNotificationPreference.user_sub == user_sub
            )
        )
        return result.scalar_one_or_none()

    async def get_preferences(self, user_sub: str) -> NotificationPreferences:
        """Return stored preferences merged against defaults."""
        row = await self._row_for_user(user_sub)
        if row is None:
            return self.defaults()
        return NotificationPreferences.model_validate(row.preferences_json)

    async def update_preferences(
        self,
        user_sub: str,
        preferences: NotificationPreferences,
    ) -> NotificationPreferences:
        """Persist the full preference object for one user."""
        row = await self._row_for_user(user_sub)

        if preferences == self.defaults():
            if row is not None:
                await self.db.delete(row)
                await self.db.commit()
            return self.defaults()

        preferences_json = preferences.model_dump(mode="json")
        if row is None:
            row = UserNotificationPreference(
                user_sub=user_sub,
                preferences_json=preferences_json,
            )
            self.db.add(row)
        else:
            row.preferences_json = preferences_json

        await self.db.commit()
        return NotificationPreferences.model_validate(row.preferences_json)
