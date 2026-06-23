"""Content-related SQLAlchemy models."""

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY, JSONB
from sqlalchemy.orm import relationship

from .base import Base, utc_now


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
