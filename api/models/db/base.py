"""SQLAlchemy declarative base and shared helpers."""

from datetime import datetime, timezone

from sqlalchemy.orm import DeclarativeBase


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    """Typed declarative base for SQLAlchemy models."""
