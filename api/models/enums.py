"""Shared enumerations for processing and task status values."""

from enum import Enum


class ProcessingStatus(str, Enum):
    """Status values for IndexedContentItem.processing_status."""

    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    REVOKED = "REVOKED"


class TaskStatus(str, Enum):
    """Status values for TaskQueue.status."""

    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SUPERSEDED = "SUPERSEDED"


class ChatRunStatus(str, Enum):
    """Status values for resumable chat generation runs."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ConversationRunMode(str, Enum):
    """Execution mode for one resumable conversation run."""

    CHAT = "chat"
    RESEARCH = "research"


class ResearchRunStatus(str, Enum):
    """Status values for resumable deep research runs."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ContentEnrichmentFineTuneJobStatus(str, Enum):
    """Status values for backend-managed content enrichment fine-tune jobs."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ContentEnrichmentModelRegistryStatus(str, Enum):
    """Status values for registered content enrichment model artifacts."""

    TRAINING = "training"
    READY = "ready"
    FAILED = "failed"
    ARCHIVED = "archived"
