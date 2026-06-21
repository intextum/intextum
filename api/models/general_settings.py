"""General (app-wide) admin settings models."""

from __future__ import annotations

from pydantic import BaseModel


class GeneralSettings(BaseModel):
    """Admin-editable app-wide settings."""

    # Public base URL the app is reachable at (scheme + host, no trailing slash),
    # used e.g. to build the API URL workers should poll. This is the admin
    # override (DB); ``None`` means unset, in which case the config default
    # (``config_public_base_url``) applies, then the request origin.
    public_base_url: str | None = None
    # Read-only default from server config (PUBLIC_BASE_URL env / config.yaml),
    # shown in the UI so admins can see what applies when no override is set.
    config_public_base_url: str | None = None


class GeneralSettingsUpdate(BaseModel):
    """Request model for updating general settings."""

    public_base_url: str | None = None
