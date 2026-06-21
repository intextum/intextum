"""Content service package."""

from .email_ingestion import (
    EmailAttachmentInput,
    EmailMessageIngestionResult,
    ingest_email_message,
)
from .service import ContentService
from .stats import ContentStatsService

__all__ = [
    "ContentService",
    "ContentStatsService",
    "EmailAttachmentInput",
    "EmailMessageIngestionResult",
    "ingest_email_message",
]
