"""Operational workflow SQLAlchemy models."""

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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base, utc_now


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


class DataSourceScanStatus(Base):
    """Live initial-scan progress for a connector (operational state, not config).

    Kept separate from ``data_sources`` so the watcher actor can write progress
    without holding write access to the admin-only connector configuration.
    """

    __tablename__ = "data_source_scan_status"

    connector_uuid = Column(
        String,
        ForeignKey("data_sources.uuid", ondelete="CASCADE"),
        primary_key=True,
    )
    state = Column(String, nullable=False, default="idle")  # idle|scanning|done|failed
    signature = Column(String, nullable=True)  # config signature of a completed scan
    dirs = Column(Integer, nullable=False, default=0)
    files_queued = Column(Integer, nullable=False, default=0)
    files_unchanged = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


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
