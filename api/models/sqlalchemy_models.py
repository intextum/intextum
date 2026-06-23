"""Backward-compatible SQLAlchemy model exports.

Model definitions live in focused modules under ``models.db``. Keep importing
from ``models.sqlalchemy_models`` until callers are migrated gradually.
"""

from models.db.base import Base, utc_now
from models.db.content import (
    ContentAuditEvent,
    ContentChunk,
    ContentItemAttachmentDetails,
    ContentItemEmailMessageDetails,
    ContentItemEnrichmentState,
    ContentItemFileDetails,
    ContentItemFolderDetails,
    IndexedContentItem,
)
from models.db.auth import (
    AppUser,
    Group,
    GroupExternalAlias,
    GroupMembership,
    LocalCredential,
    UserIdentity,
)
from models.db.workflow import (
    ChatRun,
    ContentEnrichmentFineTuneJob,
    ContentEnrichmentModelRegistry,
    Conversation,
    DataSource,
    DataSourceScanStatus,
    EventOutbox,
    Permission,
    ResearchReport,
    TaskQueue,
    Worker,
)
from models.db.settings import (
    AppSetting,
    DocumentClassCatalogEntry,
    ExtractionSchemaCatalogEntry,
    UserNotificationPreference,
)

__all__ = [
    "Base",
    "utc_now",
    "IndexedContentItem",
    "ContentItemEnrichmentState",
    "ContentChunk",
    "ContentAuditEvent",
    "ContentItemFileDetails",
    "ContentItemFolderDetails",
    "ContentItemEmailMessageDetails",
    "ContentItemAttachmentDetails",
    "AppUser",
    "UserIdentity",
    "LocalCredential",
    "Group",
    "GroupMembership",
    "GroupExternalAlias",
    "Worker",
    "Conversation",
    "DataSource",
    "DataSourceScanStatus",
    "Permission",
    "TaskQueue",
    "EventOutbox",
    "ContentEnrichmentModelRegistry",
    "ContentEnrichmentFineTuneJob",
    "ChatRun",
    "ResearchReport",
    "AppSetting",
    "DocumentClassCatalogEntry",
    "ExtractionSchemaCatalogEntry",
    "UserNotificationPreference",
]
