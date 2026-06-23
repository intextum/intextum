"""Settings and catalog SQLAlchemy models."""

from sqlalchemy import Column, DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base, utc_now


class AppSetting(Base):
    """Runtime-overridable application setting stored in the database."""

    __tablename__ = "app_settings"

    key = Column(String, primary_key=True)
    value_json = Column(JSONB, nullable=False)
    updated_by = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class DocumentClassCatalogEntry(Base):
    """First-class stored document classification label definition."""

    __tablename__ = "document_classes"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    version = Column(Integer, nullable=False, default=1, server_default=text("1"))
    description = Column(Text, nullable=False, default="")
    aliases_json = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class ExtractionSchemaCatalogEntry(Base):
    """First-class stored structured extraction schema definition."""

    __tablename__ = "extraction_schemas"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    version = Column(Integer, nullable=False, default=1, server_default=text("1"))
    document_class_id = Column(String, nullable=False)
    description = Column(Text, nullable=False, default="")
    fields_json = Column(JSONB, nullable=False, default=list)
    scenes_json = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        Index("ix_extraction_schemas_document_class_id", "document_class_id"),
    )


class UserNotificationPreference(Base):
    """Per-user notification presentation preferences."""

    __tablename__ = "user_notification_preferences"

    user_sub = Column(String, primary_key=True)
    preferences_json = Column(JSONB, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
