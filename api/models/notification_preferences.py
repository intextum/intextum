"""Typed models for per-user notification preferences."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ChatNotificationPreferences(BaseModel):
    """Toast preferences for chat lifecycle events."""

    completed: bool = True
    failed: bool = True
    cancelled: bool = False

    model_config = ConfigDict(extra="forbid")


class ContentProcessingNotificationPreferences(BaseModel):
    """Toast preferences for content processing lifecycle events."""

    completed: bool = False
    failed: bool = True

    model_config = ConfigDict(extra="forbid")


class ResearchNotificationPreferences(BaseModel):
    """Toast preferences for deep research lifecycle events."""

    completed: bool = True
    failed: bool = True
    cancelled: bool = False

    model_config = ConfigDict(extra="forbid")


class NotificationPreferences(BaseModel):
    """Top-level notification preferences for the current user."""

    chat: ChatNotificationPreferences = Field(
        default_factory=ChatNotificationPreferences
    )
    content_processing: ContentProcessingNotificationPreferences = Field(
        default_factory=ContentProcessingNotificationPreferences
    )
    research: ResearchNotificationPreferences = Field(
        default_factory=ResearchNotificationPreferences
    )

    model_config = ConfigDict(extra="forbid")
