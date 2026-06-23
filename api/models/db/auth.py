"""User and group SQLAlchemy models."""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.orm import relationship

from .base import Base, utc_now


class AppUser(Base):
    """Canonical app-owned user record."""

    __tablename__ = "app_users"

    sub = Column(
        String, primary_key=True
    )  # stable app subject id used by ACLs/ownership
    username = Column(String, nullable=False, unique=True)  # human-readable login name
    email = Column(String, nullable=True)
    display_name = Column(String, nullable=True)
    auth_display_source = Column(String, nullable=True)
    is_admin = Column(Boolean, nullable=False, default=False)
    is_disabled = Column(Boolean, nullable=False, default=False)
    session_version = Column(Integer, nullable=False, default=1)
    first_seen_at = Column(DateTime, nullable=False, default=utc_now)
    last_seen_at = Column(DateTime, nullable=False, default=utc_now)

    identities = relationship(
        "UserIdentity",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    local_credentials = relationship(
        "LocalCredential",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    group_memberships = relationship(
        "GroupMembership",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserIdentity(Base):
    """External or local login identity linked to one canonical app user."""

    __tablename__ = "user_identities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String, nullable=False)
    provider_subject = Column(String, nullable=False)
    user_sub = Column(
        String,
        ForeignKey("app_users.sub", ondelete="CASCADE"),
        nullable=False,
    )
    last_external_groups = Column(PG_ARRAY(String), nullable=True)
    first_seen_at = Column(DateTime, nullable=False, default=utc_now)
    last_seen_at = Column(DateTime, nullable=False, default=utc_now)

    user = relationship("AppUser", back_populates="identities")

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_subject",
            name="uq_user_identities_provider_subject",
        ),
        Index("ix_user_identities_user_sub", "user_sub"),
    )


class LocalCredential(Base):
    """Password credentials for a canonical app user."""

    __tablename__ = "local_credentials"

    user_sub = Column(
        String,
        ForeignKey("app_users.sub", ondelete="CASCADE"),
        primary_key=True,
    )
    password_hash = Column(String, nullable=False)
    password_changed_at = Column(DateTime, nullable=False, default=utc_now)
    must_change_password = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    user = relationship("AppUser", back_populates="local_credentials")


class Group(Base):
    """App-managed group catalog."""

    __tablename__ = "groups"

    slug = Column(String, primary_key=True)
    display_name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    memberships = relationship(
        "GroupMembership",
        back_populates="group",
        cascade="all, delete-orphan",
    )
    external_aliases = relationship(
        "GroupExternalAlias",
        back_populates="group",
        cascade="all, delete-orphan",
    )


class GroupMembership(Base):
    """Membership of a canonical user in an app-managed group."""

    __tablename__ = "group_memberships"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_slug = Column(
        String,
        ForeignKey("groups.slug", ondelete="CASCADE"),
        nullable=False,
    )
    user_sub = Column(
        String,
        ForeignKey("app_users.sub", ondelete="CASCADE"),
        nullable=False,
    )
    source = Column(String, nullable=False, default="manual")
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    group = relationship("Group", back_populates="memberships")
    user = relationship("AppUser", back_populates="group_memberships")

    __table_args__ = (
        UniqueConstraint(
            "group_slug",
            "user_sub",
            "source",
            name="uq_group_memberships_group_user_source",
        ),
        Index("ix_group_memberships_user_sub", "user_sub"),
    )


class GroupExternalAlias(Base):
    """Mapping from external provider group labels to app-managed groups."""

    __tablename__ = "group_external_aliases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_slug = Column(
        String,
        ForeignKey("groups.slug", ondelete="CASCADE"),
        nullable=False,
    )
    provider = Column(String, nullable=False)
    external_value = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    group = relationship("Group", back_populates="external_aliases")

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "external_value",
            name="uq_group_external_alias_provider_value",
        ),
        Index("ix_group_external_alias_group_slug", "group_slug"),
    )
