"""SQLAlchemy models for the intextum backend."""

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    DateTime,
    Text,
    Boolean,
    Index,
    CheckConstraint,
    ForeignKey,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship
from pgvector.sqlalchemy import Vector
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    """Typed declarative base for SQLAlchemy models."""


class Worker(Base):
    """Worker node registration."""

    __tablename__ = "workers"

    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, default="")
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    last_seen = Column(DateTime, nullable=True)
    config = Column(Text, default="{}")  # JSON stored as string
    status = Column(String, default="inactive")
    api_token = Column(String, unique=True, nullable=True)


class IndexedContentItem(Base):
    """Tracked content item status."""

    __tablename__ = "indexed_content_items"

    content_item_id = Column(String, primary_key=True)
    folder_uuid = Column(String, nullable=False)
    content_kind = Column(String, nullable=False, default="file")
    parent_content_item_id = Column(
        String,
        ForeignKey("indexed_content_items.content_item_id", ondelete="SET NULL"),
        nullable=True,
    )
    container_content_item_id = Column(
        String,
        ForeignKey("indexed_content_items.content_item_id", ondelete="SET NULL"),
        nullable=True,
    )
    external_id = Column(String, nullable=True)
    relative_path = Column(String, nullable=False)
    modified_time = Column(Float, nullable=False)
    change_time = Column(Float, nullable=False, default=0.0)
    size_bytes = Column(Integer, nullable=False)
    indexed_at = Column(DateTime, nullable=True)

    # Task Monitoring
    task_id = Column(String, nullable=True)
    task_secret = Column(
        String, nullable=True
    )  # per-task auth token for status updates
    processing_status = Column(
        String, nullable=True
    )  # QUEUED, PROCESSING, COMPLETED, FAILED, RETRYING, REVOKED, or NULL (not processed)
    processing_stage = Column(
        String, nullable=True
    )  # Live worker stage while PROCESSING (e.g. converting, chunking); NULL otherwise
    error_message = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Processing metadata
    processed_at = Column(DateTime, nullable=True)
    processed_by = Column(String, nullable=True)  # worker_id
    processing_started_at = Column(DateTime, nullable=True)
    processing_duration_ms = Column(Integer, nullable=True)
    last_processing_config = Column(JSONB, nullable=True)

    # Browsing columns
    parent_path = Column(String, nullable=False, default="")
    name = Column(String, nullable=False, default="")
    display_name = Column(String, nullable=False, default="")
    extension = Column(String, nullable=True)
    mime_type = Column(String, nullable=True)
    is_dir = Column(Boolean, nullable=False, default=False)
    is_container = Column(Boolean, nullable=False, default=False)
    is_hidden = Column(Boolean, nullable=False, default=False)
    is_symlink = Column(Boolean, nullable=False, default=False)
    last_scanned_at = Column(DateTime, nullable=True)

    # Cached ACLs for UI filtering and vector consistency (native PostgreSQL arrays)
    allowed_viewers = Column(PG_ARRAY(String), nullable=True)
    denied_viewers = Column(PG_ARRAY(String), nullable=True)

    document_json = Column(JSONB, nullable=True)
    enrichment_state = relationship(
        "ContentItemEnrichmentState",
        back_populates="content_item",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="joined",
    )
    chunks = relationship(
        "ContentChunk", back_populates="file", cascade="all, delete-orphan"
    )
    file_details = relationship(
        "ContentItemFileDetails",
        back_populates="content_item",
        cascade="all, delete-orphan",
        uselist=False,
    )
    folder_details = relationship(
        "ContentItemFolderDetails",
        back_populates="content_item",
        cascade="all, delete-orphan",
        uselist=False,
    )
    email_message_details = relationship(
        "ContentItemEmailMessageDetails",
        back_populates="content_item",
        cascade="all, delete-orphan",
        uselist=False,
    )
    attachment_details = relationship(
        "ContentItemAttachmentDetails",
        back_populates="content_item",
        cascade="all, delete-orphan",
        uselist=False,
        foreign_keys="ContentItemAttachmentDetails.content_item_id",
    )

    __table_args__ = (
        CheckConstraint(
            "content_kind IN ('file', 'folder', 'email_message', 'attachment')",
            name="ck_indexed_content_items_content_kind",
        ),
        CheckConstraint(
            "size_bytes >= 0",
            name="ck_indexed_content_items_size_non_negative",
        ),
        CheckConstraint(
            "(content_kind = 'folder' AND is_dir = true AND is_container = true) "
            "OR (content_kind <> 'folder' AND is_dir = false)",
            name="ck_indexed_content_items_kind_directory_consistency",
        ),
        Index("ix_indexed_content_items_status", "processing_status"),
        Index("ix_indexed_content_items_folder", "folder_uuid"),
        Index("ix_indexed_content_items_kind", "content_kind"),
        Index(
            "ux_indexed_content_items_external_id",
            "folder_uuid",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
        Index("ix_indexed_content_items_parent_item", "parent_content_item_id"),
        Index("ix_indexed_content_items_container_item", "container_content_item_id"),
        Index(
            "ux_indexed_content_items_path", "folder_uuid", "relative_path", unique=True
        ),
        Index(
            "ix_indexed_content_items_parent", "folder_uuid", "parent_path", "is_hidden"
        ),
        Index(
            "ix_indexed_content_items_allowed_gin",
            "allowed_viewers",
            postgresql_using="gin",
        ),
        Index(
            "ix_indexed_content_items_denied_gin",
            "denied_viewers",
            postgresql_using="gin",
        ),
    )


class ContentItemEnrichmentState(Base):
    """Normalized enrichment and review state for one content item."""

    __tablename__ = "content_item_enrichment_states"

    content_item_id = Column(
        String,
        ForeignKey("indexed_content_items.content_item_id", ondelete="CASCADE"),
        primary_key=True,
    )

    classification_system_class_id = Column(String, nullable=True)
    classification_system_label = Column(String, nullable=True)
    classification_confidence = Column(Float, nullable=True)
    classification_provider = Column(String, nullable=True)
    classification_model = Column(String, nullable=True)
    classification_status = Column(String, nullable=True)
    classification_error = Column(Text, nullable=True)
    classification_config_fingerprint = Column(String, nullable=True)
    classification_raw_json = Column(JSONB, nullable=True)
    classification_evidence_json = Column(JSONB, nullable=False, default=list)
    classification_override_class_id = Column(String, nullable=True)
    classification_override_label = Column(String, nullable=True)
    classification_effective_class_id = Column(String, nullable=True)
    classification_effective_label = Column(String, nullable=True)
    classification_review_status = Column(String, nullable=True)
    classification_dismissed_reason = Column(String, nullable=True)
    classification_reviewed_by = Column(String, nullable=True)
    classification_reviewed_by_sub = Column(String, nullable=True)
    classification_reviewed_at = Column(DateTime, nullable=True)
    classification_review_history_json = Column(JSONB, nullable=False, default=list)

    extraction_system_schema_id = Column(String, nullable=True)
    extraction_system_schema_name = Column(String, nullable=True)
    extraction_system_schema_version = Column(Integer, nullable=True)
    extraction_system_class_id = Column(String, nullable=True)
    extraction_system_class_label = Column(String, nullable=True)
    extraction_provider = Column(String, nullable=True)
    extraction_model = Column(String, nullable=True)
    extraction_status = Column(String, nullable=True)
    extraction_error = Column(Text, nullable=True)
    extraction_config_fingerprint = Column(String, nullable=True)
    extraction_raw_json = Column(JSONB, nullable=True)
    extraction_data_json = Column(JSONB, nullable=False, default=dict)
    extraction_fields_json = Column(JSONB, nullable=False, default=dict)
    extraction_summary_json = Column(JSONB, nullable=False, default=dict)
    extraction_override_data_json = Column(JSONB, nullable=True)
    extraction_override_class_id = Column(String, nullable=True)
    extraction_override_class_label = Column(String, nullable=True)
    extraction_effective_data_json = Column(JSONB, nullable=False, default=dict)
    extraction_effective_schema_id = Column(String, nullable=True)
    extraction_effective_schema_name = Column(String, nullable=True)
    extraction_effective_class_id = Column(String, nullable=True)
    extraction_effective_class_label = Column(String, nullable=True)
    extraction_review_status = Column(String, nullable=True)
    extraction_dismissed_reason = Column(String, nullable=True)
    extraction_reviewed_by = Column(String, nullable=True)
    extraction_reviewed_by_sub = Column(String, nullable=True)
    extraction_reviewed_at = Column(DateTime, nullable=True)
    extraction_review_history_json = Column(JSONB, nullable=False, default=list)

    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    content_item = relationship("IndexedContentItem", back_populates="enrichment_state")

    __table_args__ = (
        Index(
            "ix_content_item_enrichment_states_effective_class",
            "classification_effective_class_id",
            "classification_effective_label",
        ),
        Index(
            "ix_content_item_enrichment_states_effective_schema",
            "extraction_effective_schema_id",
            "extraction_effective_schema_name",
        ),
        Index(
            "ix_content_item_enrichment_states_review",
            "classification_review_status",
            "extraction_review_status",
        ),
        Index(
            "ix_content_item_enrichment_states_config",
            "classification_config_fingerprint",
            "extraction_config_fingerprint",
            "classification_provider",
            "extraction_provider",
            "extraction_model",
        ),
    )


class ContentChunk(Base):
    """Text chunks and embeddings for semantic search."""

    __tablename__ = "content_chunks"

    id = Column(String, primary_key=True)
    content_item_id = Column(
        String,
        ForeignKey("indexed_content_items.content_item_id", ondelete="CASCADE"),
        nullable=False,
    )
    text = Column(Text, nullable=False)
    # The vector size must match EMBEDDING_VECTOR_SIZE in config (1024 by default)
    embedding = Column(Vector(1024), nullable=False)
    chunk_index = Column(Integer, nullable=False)

    # Metadata for contextual search
    page_numbers = Column(PG_ARRAY(Integer), nullable=True)
    headings = Column(PG_ARRAY(String), nullable=True)
    images = Column(PG_ARRAY(String), nullable=True)
    doc_refs = Column(PG_ARRAY(String), nullable=True)
    index_version = Column(String, nullable=False)

    created_at = Column(DateTime, nullable=False, default=utc_now)

    file = relationship("IndexedContentItem", back_populates="chunks")

    __table_args__ = (Index("ix_content_chunks_content_item_id", "content_item_id"),)


class ContentAuditEvent(Base):
    """Durable audit event for one content item."""

    __tablename__ = "content_audit_events"

    id = Column(String, primary_key=True)
    content_item_id = Column(String, nullable=False)
    connector_uuid = Column(String, nullable=True)
    relative_path = Column(String, nullable=True)
    display_name = Column(String, nullable=True)
    event_type = Column(String, nullable=False)
    event_group = Column(String, nullable=False)
    status = Column(String, nullable=False)
    summary = Column(Text, nullable=False, default="")
    metadata_json = Column(JSONB, nullable=False, default=dict)
    actor_sub = Column(String, nullable=True)
    actor_name = Column(String, nullable=True)
    source = Column(String, nullable=False, default="backend")
    created_at = Column(DateTime, nullable=False, default=utc_now)

    __table_args__ = (
        Index(
            "ix_content_audit_events_item_created",
            "content_item_id",
            "created_at",
        ),
        Index("ix_content_audit_events_group", "event_group"),
        Index("ix_content_audit_events_type", "event_type"),
        Index("ix_content_audit_events_actor", "actor_sub"),
    )


class ContentItemFileDetails(Base):
    """Optional file-specific metadata for one content item."""

    __tablename__ = "content_item_file_details"

    content_item_id = Column(
        String,
        ForeignKey("indexed_content_items.content_item_id", ondelete="CASCADE"),
        primary_key=True,
    )
    checksum = Column(String, nullable=True)
    symlink_target_path = Column(String, nullable=True)
    page_count = Column(Integer, nullable=True)
    media_duration_ms = Column(Integer, nullable=True)
    image_width = Column(Integer, nullable=True)
    image_height = Column(Integer, nullable=True)

    content_item = relationship("IndexedContentItem", back_populates="file_details")


class ContentItemFolderDetails(Base):
    """Optional folder-specific metadata for one content item."""

    __tablename__ = "content_item_folder_details"

    content_item_id = Column(
        String,
        ForeignKey("indexed_content_items.content_item_id", ondelete="CASCADE"),
        primary_key=True,
    )
    child_count = Column(Integer, nullable=True)
    supports_children = Column(Boolean, nullable=False, default=True)

    content_item = relationship("IndexedContentItem", back_populates="folder_details")


class ContentItemEmailMessageDetails(Base):
    """Optional email-message metadata for one content item."""

    __tablename__ = "content_item_email_message_details"

    content_item_id = Column(
        String,
        ForeignKey("indexed_content_items.content_item_id", ondelete="CASCADE"),
        primary_key=True,
    )
    message_id_header = Column(String, nullable=True)
    thread_id = Column(String, nullable=True)
    subject = Column(String, nullable=False, default="")
    from_name = Column(String, nullable=True)
    from_address = Column(String, nullable=True)
    to_addresses_json = Column(JSONB, nullable=False, default=list)
    cc_addresses_json = Column(JSONB, nullable=False, default=list)
    bcc_addresses_json = Column(JSONB, nullable=False, default=list)
    reply_to_addresses_json = Column(JSONB, nullable=False, default=list)
    sent_at = Column(DateTime, nullable=True)
    received_at = Column(DateTime, nullable=True)
    body_text = Column(Text, nullable=True)
    body_html = Column(Text, nullable=True)
    snippet = Column(Text, nullable=True)
    has_attachments = Column(Boolean, nullable=False, default=False)

    content_item = relationship(
        "IndexedContentItem", back_populates="email_message_details"
    )


class ContentItemAttachmentDetails(Base):
    """Optional attachment metadata for one content item."""

    __tablename__ = "content_item_attachment_details"

    content_item_id = Column(
        String,
        ForeignKey("indexed_content_items.content_item_id", ondelete="CASCADE"),
        primary_key=True,
    )
    email_message_content_item_id = Column(
        String,
        ForeignKey("indexed_content_items.content_item_id", ondelete="SET NULL"),
        nullable=True,
    )
    content_id_header = Column(String, nullable=True)
    disposition = Column(String, nullable=True)
    is_inline = Column(Boolean, nullable=False, default=False)
    attachment_index = Column(Integer, nullable=True)

    content_item = relationship(
        "IndexedContentItem",
        back_populates="attachment_details",
        foreign_keys=[content_item_id],
    )


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


class Conversation(Base):
    """Materialized conversation metadata for fast user-scoped listing."""

    __tablename__ = "conversations"

    id = Column(String, primary_key=True)
    user_sub = Column(String, nullable=False)
    title = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        Index("ix_conversations_user_updated", "user_sub", "updated_at"),
        Index("ix_conversations_user_created", "user_sub", "created_at"),
    )


class DataSource(Base):
    """Configurable ingestion source."""

    __tablename__ = "data_sources"

    uuid = Column(String, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    source_type = Column(String, nullable=False, default="local_fs")
    path = Column(String, nullable=True)  # LocalFS path; NULL for S3
    watch = Column(Boolean, nullable=False, default=False)
    initial_scan = Column(Boolean, nullable=False, default=True)
    auto_process_new = Column(Boolean, nullable=False, default=True)
    immutable = Column(Boolean, nullable=False, default=False)
    force_polling = Column(Boolean, nullable=False, default=False)
    poll_interval_seconds = Column(Integer, nullable=False, default=30)
    watcher_type = Column(String, nullable=False, default="auto")
    smb_server = Column(String, nullable=True)
    smb_share = Column(String, nullable=True)
    smb_port = Column(Integer, nullable=False, default=445)
    smb_username = Column(String, nullable=True)
    smb_password = Column(String, nullable=True)  # Fernet-encrypted
    smb_domain = Column(String, nullable=True)
    # S3 fields
    endpoint_url = Column(String, nullable=True)
    bucket = Column(String, nullable=True)
    s3_prefix = Column(String, nullable=True)
    access_key = Column(String, nullable=True)
    secret_key = Column(String, nullable=True)  # Fernet-encrypted
    region = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        Index("ix_data_sources_name", "name", unique=True),
        Index("ix_data_sources_type", "source_type"),
    )


class Permission(Base):
    """Access control entry for a data folder."""

    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    folder_uuid = Column(String, nullable=False)
    trustee = Column(String, nullable=False)  # "everyone" or "sub:<oidc-sub>"
    access = Column(String, nullable=False, default="allow")  # "allow" or "deny"
    granted_by = Column(String, nullable=True)  # username who set this
    created_at = Column(DateTime, nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "folder_uuid", "trustee", name="uq_permissions_folder_trustee"
        ),
        Index("ix_permissions_folder", "folder_uuid"),
        Index("ix_permissions_trustee", "trustee"),
    )


class TaskQueue(Base):
    """HTTP-based task queue replacing Celery."""

    __tablename__ = "task_queue"

    id = Column(String, primary_key=True)  # UUID
    task_type = Column(String, nullable=False)  # "process" or training task
    content_kind = Column(
        String, nullable=True
    )  # "document", "video", "image", "training", or NULL when capability is unknown
    content_item_id = Column(String, nullable=True)
    folder_uuid = Column(String, nullable=False)
    relative_path = Column(String, nullable=False)
    metadata_json = Column(Text, nullable=True)  # JSON blob
    status = Column(
        String, nullable=False, default="PENDING"
    )  # PENDING, CLAIMED, COMPLETED, FAILED, SUPERSEDED
    requested_by_sub = Column(String, nullable=True)
    claimed_by = Column(String, nullable=True)  # worker_id
    claimed_at = Column(DateTime, nullable=True)
    stage = Column(String, nullable=True)  # Live worker stage reported via heartbeat
    stage_updated_at = Column(DateTime, nullable=True)
    task_secret = Column(String, nullable=True)  # per-task auth
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        Index("ix_task_queue_claim", "status", "content_kind", "created_at"),
        Index("ix_task_queue_stale", "status", "claimed_at"),
        Index("ix_task_queue_supersede", "content_item_id", "created_at"),
        Index("ix_task_queue_requested_by_created", "requested_by_sub", "created_at"),
    )


class EventOutbox(Base):
    """Durable side-effect queue for user events and post-processing actions."""

    __tablename__ = "event_outbox"

    id = Column(String, primary_key=True)
    event_type = Column(String, nullable=False)
    aggregate_type = Column(String, nullable=False)
    aggregate_id = Column(String, nullable=False)
    user_sub = Column(String, nullable=True)
    payload_json = Column(JSONB, nullable=False, default=dict)
    status = Column(String, nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        Index("ix_event_outbox_status_next", "status", "next_attempt_at"),
        Index("ix_event_outbox_aggregate", "aggregate_type", "aggregate_id"),
    )


class ContentEnrichmentModelRegistry(Base):
    """Registered fine-tuned content enrichment model artifacts."""

    __tablename__ = "content_enrichment_model_registry"

    id = Column(String, primary_key=True)
    target_kind = Column(String, nullable=False)
    training_method = Column(String, nullable=False, default="lora")
    status = Column(String, nullable=False, default="training")
    base_model = Column(String, nullable=False)
    target_name = Column(String, nullable=True)
    config_fingerprint = Column(String, nullable=False)
    reviewed_example_count = Column(Integer, nullable=False, default=0)
    artifact_path = Column(String, nullable=True)
    metrics_json = Column(JSONB, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        Index(
            "ix_content_enrichment_model_registry_kind_target_created",
            "target_kind",
            "target_name",
            "created_at",
        ),
    )


class ContentEnrichmentFineTuneJob(Base):
    """Durable backend records for content enrichment adapter training jobs."""

    __tablename__ = "content_enrichment_fine_tune_jobs"

    id = Column(String, primary_key=True)
    registry_model_id = Column(
        String,
        ForeignKey("content_enrichment_model_registry.id", ondelete="CASCADE"),
        nullable=False,
    )
    queue_task_id = Column(String, nullable=True)
    status = Column(String, nullable=False, default="queued")
    target_kind = Column(String, nullable=False)
    training_method = Column(String, nullable=False, default="lora")
    base_model = Column(String, nullable=False)
    target_name = Column(String, nullable=True)
    config_fingerprint = Column(String, nullable=False)
    dataset_summary_json = Column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    config_snapshot_json = Column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    error_message = Column(Text, nullable=True)
    requested_by = Column(String, nullable=True)
    requested_by_sub = Column(String, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        Index(
            "ix_content_enrichment_fine_tune_jobs_status_created",
            "status",
            "created_at",
        ),
        Index(
            "ix_content_enrichment_fine_tune_jobs_registry_model_id",
            "registry_model_id",
        ),
    )


class ChatRun(Base):
    """Durable metadata for one resumable LangGraph chat run."""

    __tablename__ = "chat_runs"

    id = Column(String, primary_key=True)
    conversation_id = Column(String, nullable=False)
    user_sub = Column(String, nullable=False)
    mode = Column("mode", String, nullable=False, default="chat", quote=True)
    research_report_id = Column(
        String,
        ForeignKey("research_reports.id", ondelete="SET NULL"),
        nullable=True,
    )
    status = Column(String, nullable=False, default="PENDING")
    request_json = Column(JSONB, nullable=False)
    claimed_by = Column(String, nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    last_event_id = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        Index("ix_chat_runs_user_created", "user_sub", "created_at"),
        Index("ix_chat_runs_conversation_created", "conversation_id", "created_at"),
        Index("ix_chat_runs_status_created", "status", "created_at"),
        Index(
            "ux_chat_runs_active_conversation",
            "conversation_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'RUNNING')"),
        ),
    )


class ResearchReport(Base):
    """Persisted deep research report artifact."""

    __tablename__ = "research_reports"

    id = Column(String, primary_key=True)
    conversation_id = Column(String, nullable=False)
    user_sub = Column(String, nullable=False)
    title = Column(Text, nullable=True)
    prompt = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="PENDING")
    context_file_paths_json = Column(JSONB, nullable=False, default=list)
    outline_json = Column(JSONB, nullable=False, default=list)
    sections_json = Column(JSONB, nullable=False, default=list)
    sources_json = Column(JSONB, nullable=False, default=list)
    images_json = Column(JSONB, nullable=False, default=list)
    verification_json = Column(JSONB, nullable=False, default=list)
    content_markdown = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        Index(
            "ix_research_reports_conversation_updated", "conversation_id", "updated_at"
        ),
        Index("ix_research_reports_user_updated", "user_sub", "updated_at"),
        Index("ix_research_reports_status_created", "status", "created_at"),
    )


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
