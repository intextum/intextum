"""Helper functions for file service."""

from datetime import datetime

import humanize

from sqlalchemy import func, inspect
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import NO_VALUE

from config import BaseDataConnector
from models.content.items import (
    ContentItemAttachmentDetails,
    ContentItemEmailMessageDetails,
    ContentItemFileDetails,
    ContentItemInfo,
    ContentItemKind,
    ContentItemRelationSummary,
    ContentItemFolderDetails,
    ContentItemProcessingModeSummary,
    FolderInfo,
    ContentItemType,
)
from models.ai_settings import EffectiveAiSettings
from models.sqlalchemy_models import IndexedContentItem
from models.user import User
from services.content.enrichment import build_content_enrichment_api_views
from services.content.invariants import safe_content_item_kind
from services.content.location import render_api_path, split_api_path
from services.content.policy import content_item_capabilities
from services.utils import find_folder_by_name
from trustees import build_user_trustees


def _api_path(folder: BaseDataConnector, relative_path: str) -> str:
    return render_api_path(folder, relative_path)


def _is_acl_admin(user: User | None) -> bool:
    return bool(user and user.is_admin)


def format_size(size_bytes: int) -> str:
    """Format file size in human readable format."""
    return humanize.naturalsize(size_bytes)


def resolve_db_context(api_path: str) -> tuple[BaseDataConnector, str]:
    """Convert a folder-name-prefixed API path to (DataSource, folder-relative-path).

    API paths are `{folder_name}/{relative_path}`.
    Raises FileNotFoundError if no matching data source is found.
    """
    folder_name, rest = split_api_path(api_path)

    folder = find_folder_by_name(folder_name)
    if not folder:
        raise FileNotFoundError(f"No folder named: {folder_name}")

    return folder, rest


def user_can_access_acl(
    allowed_viewers: list[str] | None,
    denied_viewers: list[str] | None,
    user: User | None,
) -> bool:
    """In-memory ACL check for a pair of allow/deny trustee lists."""
    if _is_acl_admin(user):
        return True

    trustees = build_user_trustees(user)
    if denied_viewers and any(t in denied_viewers for t in trustees):
        return False

    if allowed_viewers:
        return any(t in allowed_viewers for t in trustees)

    return False


def user_can_access_record(rec: IndexedContentItem, user: User | None) -> bool:
    """In-memory ACL check on a DB record."""
    return user_can_access_acl(rec.allowed_viewers, rec.denied_viewers, user)


def summarize_processing_mode(
    processing_config: dict[str, object] | None,
) -> ContentItemProcessingModeSummary | None:
    """Build a stable processing-mode summary from persisted processing config."""
    if not processing_config:
        return None

    enrichment_only = bool(processing_config.get("enrichment_only"))
    document_enrichment = bool(processing_config.get("document_enrichment"))

    if not enrichment_only:
        return ContentItemProcessingModeSummary(
            mode="full",
            enrichment_only=False,
            document_enrichment=document_enrichment,
        )

    return ContentItemProcessingModeSummary(
        mode="enrichment_only",
        enrichment_only=True,
        document_enrichment=True,
    )


def _loaded_relationship(rec: IndexedContentItem, key: str):
    """Return a relationship value only when it is already loaded."""
    loaded_value = inspect(rec).attrs[key].loaded_value
    if loaded_value is NO_VALUE:
        return None
    return loaded_value


def _record_file_details(rec: IndexedContentItem) -> ContentItemFileDetails | None:
    details = _loaded_relationship(rec, "file_details")
    if details is None:
        return None
    return ContentItemFileDetails(
        checksum=details.checksum,
        symlink_target_path=details.symlink_target_path,
        page_count=details.page_count,
        media_duration_ms=details.media_duration_ms,
        image_width=details.image_width,
        image_height=details.image_height,
    )


def _record_folder_details(
    rec: IndexedContentItem, *, child_count: int | None = None
) -> ContentItemFolderDetails:
    details = _loaded_relationship(rec, "folder_details")
    if details is not None:
        return ContentItemFolderDetails(
            child_count=child_count if child_count is not None else details.child_count,
            supports_children=details.supports_children,
        )
    return ContentItemFolderDetails(
        child_count=child_count,
        supports_children=bool(rec.is_container or rec.is_dir),
    )


def _record_email_message_details(
    rec: IndexedContentItem,
) -> ContentItemEmailMessageDetails | None:
    details = _loaded_relationship(rec, "email_message_details")
    if details is None:
        return None
    return ContentItemEmailMessageDetails(
        message_id_header=details.message_id_header,
        thread_id=details.thread_id,
        subject=details.subject,
        from_name=details.from_name,
        from_address=details.from_address,
        to_addresses=details.to_addresses_json or [],
        cc_addresses=details.cc_addresses_json or [],
        bcc_addresses=details.bcc_addresses_json or [],
        reply_to_addresses=details.reply_to_addresses_json or [],
        sent_at=details.sent_at,
        received_at=details.received_at,
        body_text=details.body_text,
        body_html=details.body_html,
        snippet=details.snippet,
        has_attachments=details.has_attachments,
    )


def _record_attachment_details(
    rec: IndexedContentItem,
) -> ContentItemAttachmentDetails | None:
    details = _loaded_relationship(rec, "attachment_details")
    if details is None:
        return None
    return ContentItemAttachmentDetails(
        email_message_content_item_id=details.email_message_content_item_id,
        content_id_header=details.content_id_header,
        disposition=details.disposition,
        is_inline=details.is_inline,
        attachment_index=details.attachment_index,
    )


def record_to_relation_summary(
    rec: IndexedContentItem,
    folder: BaseDataConnector,
) -> ContentItemRelationSummary:
    """Build a compact relation summary for parent/child content references."""
    content_kind = safe_content_item_kind(rec.content_kind)
    return ContentItemRelationSummary(
        id=rec.content_item_id,
        display_name=rec.display_name or rec.name or rec.relative_path,
        path=_api_path(folder, rec.relative_path),
        kind=content_kind,
        mime_type=rec.mime_type,
    )


async def user_can_access_folder_uuid(
    db: AsyncSession, folder_uuid: str, user: User | None
) -> bool:
    """Authorize user against folder-level permissions when a file row is missing."""
    from services.permission import PermissionService

    allowed, denied = await PermissionService(db).compute_effective_viewers(folder_uuid)
    return user_can_access_acl(allowed or None, denied or None, user)


async def get_record(
    db: AsyncSession, content_item_id: str
) -> IndexedContentItem | None:
    """Fetch a single IndexedContentItem by content_item_id."""
    stmt = select(IndexedContentItem).where(
        IndexedContentItem.content_item_id == content_item_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def record_to_file_info(
    rec: IndexedContentItem,
    folder: BaseDataConnector,
    *,
    effective_settings: EffectiveAiSettings | None = None,
) -> ContentItemInfo:
    """Build ContentItemInfo from an IndexedContentItem DB record."""
    file_type = ContentItemType.SYMLINK if rec.is_symlink else ContentItemType.FILE
    content_kind = safe_content_item_kind(rec.content_kind)
    classification, extraction, enrichment = build_content_enrichment_api_views(
        rec,
        effective_settings,
    )

    return ContentItemInfo(
        id=rec.content_item_id,
        name=rec.name,
        display_name=rec.display_name or rec.name,
        path=_api_path(folder, rec.relative_path),
        kind=content_kind,
        type=file_type,
        parent_content_item_id=rec.parent_content_item_id,
        container_content_item_id=rec.container_content_item_id,
        external_id=rec.external_id,
        extension=rec.extension,
        mime_type=rec.mime_type,
        size_bytes=rec.size_bytes or 0,
        size_human=format_size(rec.size_bytes or 0),
        modified_at=datetime.fromtimestamp(rec.modified_time)
        if rec.modified_time
        else datetime.min,
        created_at=datetime.fromtimestamp(rec.change_time) if rec.change_time else None,
        accessed_at=None,
        is_container=bool(rec.is_container),
        is_hidden=rec.is_hidden,
        is_symlink=rec.is_symlink,
        inode=None,
        file_details=_record_file_details(rec),
        folder_details=_record_folder_details(rec)
        if rec.is_dir or content_kind == ContentItemKind.FOLDER
        else None,
        email_message_details=_record_email_message_details(rec),
        attachment_details=_record_attachment_details(rec),
        capabilities=content_item_capabilities(content_kind),
        status=rec.processing_status,
        processing_stage=rec.processing_stage,
        processing_error=rec.error_message,
        processed_at=rec.processed_at,
        processed_by=rec.processed_by,
        processing_duration_ms=rec.processing_duration_ms,
        processing_mode=summarize_processing_mode(rec.last_processing_config),
        last_processing_config=rec.last_processing_config,
        review_state=enrichment.review_state,
        immutable=getattr(folder, "immutable", False),
        document_classification=classification,
        document_extraction=extraction,
        document_enrichment=enrichment,
    )


async def record_to_folder_info(
    db: AsyncSession,
    rec: IndexedContentItem,
    folder: BaseDataConnector,
    user: User | None = None,
) -> FolderInfo:
    """Build FolderInfo from a directory record, with item_count and total_size from SQL."""
    child_parent = rec.relative_path
    stats_stmt = select(
        func.count(IndexedContentItem.content_item_id),
        func.coalesce(func.sum(IndexedContentItem.size_bytes), 0),
    ).where(
        IndexedContentItem.folder_uuid == folder.uuid,
        IndexedContentItem.parent_path == child_parent,
        IndexedContentItem.is_hidden.is_(False),
    )
    result = await db.execute(stats_stmt)
    item_count, total_size = result.fetchone() or (0, 0)

    return FolderInfo(
        id=rec.content_item_id,
        name=rec.name or folder.name,
        display_name=rec.display_name or rec.name or folder.name,
        path=_api_path(folder, rec.relative_path),
        kind=ContentItemKind.FOLDER,
        modified_at=datetime.fromtimestamp(rec.modified_time)
        if rec.modified_time
        else datetime.min,
        parent_content_item_id=rec.parent_content_item_id,
        container_content_item_id=rec.container_content_item_id,
        external_id=rec.external_id,
        mime_type=rec.mime_type,
        item_count=int(item_count or 0),
        total_size_bytes=int(total_size or 0),
        is_container=True if rec.is_container is None else bool(rec.is_container),
        folder_details=_record_folder_details(rec, child_count=int(item_count or 0)),
    )


async def batch_record_to_folder_info(
    db: AsyncSession,
    records: list[IndexedContentItem],
    folder: BaseDataConnector,
    user: User | None = None,
) -> list[FolderInfo]:
    """Build FolderInfo list from directory records with a single batched stats query."""
    if not records:
        return []

    parent_paths = [r.relative_path for r in records]

    stats_stmt = (
        select(
            IndexedContentItem.parent_path,
            func.count(IndexedContentItem.content_item_id),
            func.coalesce(func.sum(IndexedContentItem.size_bytes), 0),
        )
        .where(
            IndexedContentItem.folder_uuid == folder.uuid,
            IndexedContentItem.parent_path.in_(parent_paths),
            IndexedContentItem.is_hidden.is_(False),
        )
        .group_by(IndexedContentItem.parent_path)
    )
    result = await db.execute(stats_stmt)
    stats_map = {row[0]: (int(row[1] or 0), int(row[2] or 0)) for row in result.all()}

    return [
        FolderInfo(
            id=rec.content_item_id,
            name=rec.name or folder.name,
            display_name=rec.display_name or rec.name or folder.name,
            path=_api_path(folder, rec.relative_path),
            kind=ContentItemKind.FOLDER,
            modified_at=datetime.fromtimestamp(rec.modified_time)
            if rec.modified_time
            else datetime.min,
            parent_content_item_id=rec.parent_content_item_id,
            container_content_item_id=rec.container_content_item_id,
            external_id=rec.external_id,
            mime_type=rec.mime_type,
            item_count=stats_map.get(rec.relative_path, (0, 0))[0],
            total_size_bytes=stats_map.get(rec.relative_path, (0, 0))[1],
            is_container=True if rec.is_container is None else bool(rec.is_container),
            folder_details=_record_folder_details(
                rec, child_count=stats_map.get(rec.relative_path, (0, 0))[0]
            ),
        )
        for rec in records
    ]
