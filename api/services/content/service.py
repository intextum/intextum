"""File service for browsing and managing files — DB-driven."""

from dataclasses import dataclass
from datetime import datetime
import logging
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from config import BaseDataConnector, get_settings
from models.content.items import (
    ContentProcessingTaskInfo,
    ContentItemInfo,
    ContentItemKind,
    ContentItemFolderDetails,
    FolderInfo,
    ContentItemType,
    ContentItemTreeNode,
    ContentItemListResponse,
    ContentTreeResponse,
)
from models.sqlalchemy_models import (
    ContentItemAttachmentDetails,
    IndexedContentItem,
    TaskQueue,
)
from models.user import User
from services.ai_settings import AiSettingsService
from services.connector import ConnectorRuntimeService
from services.utils import compute_content_item_id
from .access import resolve_source_target
from .helpers import (
    batch_record_to_folder_info,
    get_record,
    record_to_file_info,
    record_to_folder_info,
    record_to_relation_summary,
    resolve_db_context,
    user_can_access_folder_uuid,
    user_can_access_record,
)
from .reconcile import Reconciler

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedPathContext:
    stripped_path: str
    folder: BaseDataConnector | None
    folder_rel_path: str


class ContentService:
    """Service for file browsing operations — PostgreSQL as single source of truth."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()
        self.reconciler = Reconciler(db)
        self.connectors = ConnectorRuntimeService(db)

    async def _source_accessible(
        self, source: BaseDataConnector, user: User | None
    ) -> bool:
        root_id = compute_content_item_id(source.uuid, "")
        root_rec = await get_record(self.db, root_id)
        if root_rec:
            return user_can_access_record(root_rec, user)
        return await user_can_access_folder_uuid(self.db, source.uuid, user)

    async def _accessible_sources(self, user: User | None) -> list[BaseDataConnector]:
        accessible: list[BaseDataConnector] = []
        for source in self.connectors.browsable_connectors():
            if await self._source_accessible(source, user):
                accessible.append(source)
        return accessible

    async def _ensure_directory_access(
        self, folder: BaseDataConnector, folder_rel_path: str, user: User | None
    ) -> None:
        dir_id = compute_content_item_id(folder.uuid, folder_rel_path or "")
        dir_rec = await get_record(self.db, dir_id)
        if dir_rec:
            if not user_can_access_record(dir_rec, user):
                raise PermissionError("Access denied")
            return

        if not await user_can_access_folder_uuid(self.db, folder.uuid, user):
            raise PermissionError("Access denied")

    @staticmethod
    def _children_stmt(
        folder_uuid: str,
        folder_rel_path: str,
        include_hidden: bool,
    ):
        stmt = select(IndexedContentItem).where(
            IndexedContentItem.folder_uuid == folder_uuid,
            IndexedContentItem.parent_path == (folder_rel_path or ""),
            IndexedContentItem.relative_path != (folder_rel_path or ""),
        )
        if not include_hidden:
            stmt = stmt.where(IndexedContentItem.is_hidden.is_(False))
        return stmt

    async def _has_children(
        self,
        folder: BaseDataConnector,
        folder_rel_path: str,
        user: User | None,
        include_hidden: bool,
    ) -> bool:
        stmt = (
            self._children_stmt(folder.uuid, folder_rel_path, include_hidden)
            .with_only_columns(IndexedContentItem.content_item_id)
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none() is not None

    async def _list_child_records(
        self,
        folder: BaseDataConnector,
        folder_rel_path: str,
        user: User | None,
        include_hidden: bool,
    ) -> list[IndexedContentItem]:
        stmt = self._children_stmt(folder.uuid, folder_rel_path, include_hidden)
        stmt = stmt.order_by(
            IndexedContentItem.is_dir.desc(), func.lower(IndexedContentItem.name)
        )
        return (await self.db.execute(stmt)).scalars().all()

    async def _root_folder_stats(
        self, source: BaseDataConnector, user: User | None
    ) -> tuple[int, int]:
        stmt = select(
            func.count(IndexedContentItem.content_item_id),
            func.coalesce(func.sum(IndexedContentItem.size_bytes), 0),
        ).where(
            IndexedContentItem.folder_uuid == source.uuid,
            IndexedContentItem.parent_path == "",
            IndexedContentItem.relative_path != "",
            IndexedContentItem.is_hidden.is_(False),
        )
        result = await self.db.execute(stmt)
        item_count, total_size = result.fetchone() or (0, 0)
        return int(item_count or 0), int(total_size or 0)

    async def _root_folder_info(
        self, source: BaseDataConnector, user: User | None
    ) -> FolderInfo:
        item_count, total_size = await self._root_folder_stats(source, user)
        return FolderInfo(
            id=source.uuid,
            name=source.name,
            display_name=source.name,
            path=source.name,
            kind=ContentItemKind.FOLDER,
            modified_at=datetime.min,
            item_count=item_count,
            total_size_bytes=total_size,
            is_container=True,
            folder_details=ContentItemFolderDetails(
                child_count=item_count,
                supports_children=True,
            ),
        )

    async def _records_to_listing_parts(
        self,
        records: list[IndexedContentItem],
        folder: BaseDataConnector,
        user: User | None,
        *,
        effective_settings=None,
    ) -> tuple[list[FolderInfo], list[ContentItemInfo], int]:
        dir_records = [r for r in records if r.is_dir]
        file_records = [r for r in records if not r.is_dir]

        folders = await batch_record_to_folder_info(
            self.db, dir_records, folder, user=user
        )

        files: list[ContentItemInfo] = []
        total_size = 0
        for rec in file_records:
            file_info = record_to_file_info(
                rec,
                folder,
                effective_settings=effective_settings,
            )
            files.append(file_info)
            total_size += file_info.size_bytes

        return folders, files, total_size

    async def _maybe_reconcile(
        self, folder: BaseDataConnector, folder_rel_path: str
    ) -> None:
        # Watched connectors still need on-demand reconcile while background scans
        # are catching up or when watcher events were missed.
        await self.reconciler.maybe_reconcile(folder, folder_rel_path)

    @staticmethod
    def _strip_relative_path(relative_path: str) -> str:
        return relative_path.strip("/")

    async def _attach_processing_task_info(
        self, file_info: ContentItemInfo, rec: IndexedContentItem
    ) -> None:
        if not rec.task_id:
            return

        result = await self.db.execute(
            select(TaskQueue).where(TaskQueue.id == rec.task_id)
        )
        task = result.scalar_one_or_none()
        if task is None:
            file_info.processing_task = ContentProcessingTaskInfo(
                id=rec.task_id,
                task_type="process",
                status=rec.processing_status or "UNKNOWN",
                error_message=rec.error_message,
            )
            return

        file_info.processing_task = ContentProcessingTaskInfo(
            id=task.id,
            task_type=task.task_type,
            content_kind=task.content_kind,
            status=task.status,
            claimed_by=task.claimed_by,
            claimed_at=task.claimed_at,
            retry_count=task.retry_count or 0,
            max_retries=task.max_retries or 0,
            error_message=task.error_message,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    async def _path_context(self, relative_path: str) -> ResolvedPathContext:
        stripped_path = self._strip_relative_path(relative_path)
        if not stripped_path:
            return ResolvedPathContext(
                stripped_path=stripped_path,
                folder=None,
                folder_rel_path="",
            )

        try:
            folder, folder_rel_path = resolve_db_context(stripped_path)
        except FileNotFoundError:
            await self.connectors.refresh()
            folder, folder_rel_path = resolve_db_context(stripped_path)
        return ResolvedPathContext(
            stripped_path=stripped_path,
            folder=folder,
            folder_rel_path=folder_rel_path,
        )

    @staticmethod
    def _parent_path_for(stripped_path: str) -> str | None:
        if not stripped_path:
            return None
        parts = stripped_path.split("/")
        if len(parts) <= 1:
            return ""
        return "/".join(parts[:-1])

    @staticmethod
    def _node_name(
        folder: BaseDataConnector, folder_rel_path: str, rec: IndexedContentItem | None
    ) -> str:
        if rec and rec.name:
            return rec.name
        if folder_rel_path:
            return Path(folder_rel_path).name
        return folder.name

    @staticmethod
    def _api_path(folder: BaseDataConnector, folder_rel_path: str) -> str:
        return f"{folder.name}/{folder_rel_path}" if folder_rel_path else folder.name

    async def _tree_node_state(
        self,
        folder: BaseDataConnector,
        folder_rel_path: str,
        user: User | None,
        include_hidden: bool,
    ) -> tuple[str, IndexedContentItem | None, bool, bool]:
        content_item_id = compute_content_item_id(folder.uuid, folder_rel_path or "")
        rec = await get_record(self.db, content_item_id)
        is_dir = rec.is_dir if rec else (not folder_rel_path)
        has_children = (
            await self._has_children(folder, folder_rel_path, user, include_hidden)
            if is_dir
            else False
        )
        return content_item_id, rec, is_dir, has_children

    async def _tree_children(
        self,
        folder: BaseDataConnector,
        folder_rel_path: str,
        user: User | None,
        depth: int,
        include_hidden: bool,
        *,
        is_dir: bool,
    ) -> list[ContentItemTreeNode] | None:
        if not is_dir or depth <= 0:
            return None
        await self._maybe_reconcile(folder, folder_rel_path)
        child_records = await self._list_child_records(
            folder, folder_rel_path, user, include_hidden
        )
        children: list[ContentItemTreeNode] = []
        for child_rec in child_records:
            children.append(
                await self._build_tree_node(
                    folder, child_rec.relative_path, user, depth - 1, include_hidden
                )
            )
        return children

    async def _tree_details(
        self,
        rec: IndexedContentItem | None,
        *,
        is_dir: bool,
        folder: BaseDataConnector,
        user: User | None,
    ) -> FolderInfo | ContentItemInfo | None:
        if not rec:
            return None
        if is_dir:
            return await record_to_folder_info(self.db, rec, folder, user=user)
        effective_settings = await AiSettingsService(self.db).get_effective_settings()
        return record_to_file_info(
            rec,
            folder,
            effective_settings=effective_settings,
        )

    @staticmethod
    def _tree_file_type(
        rec: IndexedContentItem | None, *, is_dir: bool
    ) -> ContentItemType:
        if rec and rec.is_symlink:
            return ContentItemType.SYMLINK
        return ContentItemType.FOLDER if is_dir else ContentItemType.FILE

    async def _root_tree_children(
        self,
        user: User | None,
        depth: int,
        include_hidden: bool,
    ) -> list[ContentItemTreeNode] | None:
        if depth <= 0:
            return None
        return [
            await self._build_tree_node(source, "", user, depth - 1, include_hidden)
            for source in await self._accessible_sources(user)
        ]

    @staticmethod
    def _root_tree_node(
        children: list[ContentItemTreeNode] | None,
    ) -> ContentItemTreeNode:
        return ContentItemTreeNode(
            id="root",
            name="Root",
            display_name="Root",
            path="",
            kind=ContentItemKind.FOLDER,
            type=ContentItemType.FOLDER,
            children=children,
            is_expanded=children is not None,
            has_children=bool(children),
            details=None,
        )

    async def _list_root_directory(self, user: User | None) -> ContentItemListResponse:
        virtual_folders = [
            await self._root_folder_info(source, user)
            for source in await self._accessible_sources(user)
        ]
        return ContentItemListResponse(
            path="",
            parent_path=None,
            folders=virtual_folders,
            files=[],
            total_items=len(virtual_folders),
            total_size_bytes=0,
        )

    async def _list_source_directory(
        self,
        context: ResolvedPathContext,
        user: User | None,
        include_hidden: bool,
    ) -> ContentItemListResponse:
        if context.folder is None:
            raise ValueError("source context is required")

        folder = context.folder
        folder_rel_path = context.folder_rel_path
        await self._ensure_directory_access(folder, folder_rel_path, user)
        await self._maybe_reconcile(folder, folder_rel_path)
        records = await self._list_child_records(
            folder, folder_rel_path, user, include_hidden
        )
        effective_settings = await AiSettingsService(self.db).get_effective_settings()
        folders, files, total_size = await self._records_to_listing_parts(
            records, folder, user, effective_settings=effective_settings
        )

        return ContentItemListResponse(
            path=context.stripped_path,
            parent_path=self._parent_path_for(context.stripped_path),
            folders=folders,
            files=files,
            total_items=len(folders) + len(files),
            total_size_bytes=total_size,
            immutable=getattr(folder, "immutable", False),
        )

    async def list_directory(
        self,
        relative_path: str = "",
        user: User | None = None,
        include_hidden: bool = False,
    ) -> ContentItemListResponse:
        """List files and folders in a directory (pure DB, no filesystem iteration)."""
        context = await self._path_context(relative_path)

        if context.folder is None:
            return await self._list_root_directory(user)

        return await self._list_source_directory(context, user, include_hidden)

    async def _tree_node_for_context(
        self,
        context: ResolvedPathContext,
        user: User | None,
        depth: int,
        include_hidden: bool,
    ) -> ContentItemTreeNode:
        if context.folder is None:
            children = await self._root_tree_children(user, depth, include_hidden)
            return self._root_tree_node(children)

        await self._ensure_directory_access(
            context.folder, context.folder_rel_path, user
        )
        return await self._build_tree_node(
            context.folder,
            context.folder_rel_path,
            user,
            depth,
            include_hidden,
        )

    async def get_tree_node(
        self,
        relative_path: str = "",
        user: User | None = None,
        depth: int = 1,
        include_hidden: bool = False,
    ) -> ContentItemTreeNode:
        """Get a tree node for a directory."""
        context = await self._path_context(relative_path)
        return await self._tree_node_for_context(context, user, depth, include_hidden)

    async def _build_tree_node(
        self,
        folder: BaseDataConnector,
        folder_rel_path: str,
        user: User | None,
        depth: int,
        include_hidden: bool,
    ) -> ContentItemTreeNode:
        """Recursively build a tree node from DB."""
        content_item_id, rec, is_dir, has_children = await self._tree_node_state(
            folder, folder_rel_path, user, include_hidden
        )
        children = await self._tree_children(
            folder, folder_rel_path, user, depth, include_hidden, is_dir=is_dir
        )
        details = await self._tree_details(rec, is_dir=is_dir, folder=folder, user=user)
        file_type = self._tree_file_type(rec, is_dir=is_dir)

        return ContentItemTreeNode(
            id=content_item_id,
            name=self._node_name(folder, folder_rel_path, rec),
            display_name=(rec.display_name if rec else None)
            or self._node_name(folder, folder_rel_path, rec),
            path=self._api_path(folder, folder_rel_path),
            kind=ContentItemKind.FOLDER if is_dir else ContentItemKind.FILE,
            type=file_type,
            children=children,
            is_expanded=children is not None,
            has_children=has_children,
            details=details,
        )

    async def get_file_tree(
        self,
        relative_path: str = "",
        user: User | None = None,
        depth: int = 1,
        include_hidden: bool = False,
    ) -> ContentTreeResponse:
        """Get a file tree response."""
        context = await self._path_context(relative_path)
        tree_node = await self._tree_node_for_context(
            context, user, depth, include_hidden
        )
        immutable = (
            getattr(context.folder, "immutable", False) if context.folder else False
        )
        return ContentTreeResponse(root=tree_node, depth=depth, immutable=immutable)

    async def get_file_details(
        self, relative_path: str, user: User | None = None
    ) -> ContentItemInfo:
        """Get detailed information about a specific file (DB + optional adapter enrichment)."""
        resolved = await resolve_source_target(
            self.db,
            relative_path,
            user,
            expect_dir=False,
            allow_unindexed=False,
        )
        rec = resolved.record
        if rec is None:
            raise FileNotFoundError(f"File not indexed: {relative_path}")

        adapter = resolved.folder.get_adapter()
        effective_settings = await AiSettingsService(self.db).get_effective_settings()
        file_info = record_to_file_info(
            rec,
            resolved.folder,
            effective_settings=effective_settings,
        )
        await self._attach_processing_task_info(file_info, rec)

        local_path = await adapter.get_local_path(rec.relative_path)
        if local_path and local_path.is_file():
            try:
                file_stat = local_path.stat()
                file_info.accessed_at = datetime.fromtimestamp(file_stat.st_atime)
                file_info.inode = file_stat.st_ino
            except OSError:
                logger.debug(
                    "Unable to enrich file details from local path %s",
                    local_path,
                    exc_info=True,
                )

        if rec.parent_content_item_id:
            parent_record = await get_record(self.db, rec.parent_content_item_id)
            if (
                parent_record is not None
                and parent_record.folder_uuid == rec.folder_uuid
                and user_can_access_record(parent_record, user)
            ):
                file_info.parent_item = record_to_relation_summary(
                    parent_record, resolved.folder
                )

        if rec.content_kind == ContentItemKind.EMAIL_MESSAGE.value:
            child_stmt = (
                select(IndexedContentItem)
                .where(
                    IndexedContentItem.parent_content_item_id == rec.content_item_id,
                    IndexedContentItem.folder_uuid == rec.folder_uuid,
                )
                .order_by(
                    func.coalesce(
                        ContentItemAttachmentDetails.attachment_index, 10_000
                    ),
                    func.lower(IndexedContentItem.display_name),
                )
            )
            child_stmt = child_stmt.outerjoin(
                ContentItemAttachmentDetails,
                ContentItemAttachmentDetails.content_item_id
                == IndexedContentItem.content_item_id,
            )
            child_records = (await self.db.execute(child_stmt)).scalars().all()
            file_info.child_items = [
                record_to_relation_summary(child_record, resolved.folder)
                for child_record in child_records
            ]

        return file_info

    async def get_file_details_by_id(
        self, content_item_id: str, user: User | None = None
    ) -> ContentItemInfo:
        """Get detailed information about a specific file by content item id."""
        rec = await get_record(self.db, content_item_id)
        if rec is None:
            raise FileNotFoundError(f"File not indexed: {content_item_id}")
        if not user_can_access_record(rec, user):
            raise PermissionError("Access denied")

        folder = await self.connectors.get_connector_or_refresh(rec.folder_uuid)
        if folder is None:
            raise FileNotFoundError(f"Connector not found: {rec.folder_uuid}")

        return await self.get_file_details(f"{folder.name}/{rec.relative_path}", user)
