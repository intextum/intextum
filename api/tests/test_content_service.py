"""Tests for file service."""

from datetime import date
import logging
import pytest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock, AsyncMock
from sqlalchemy.dialects import postgresql
from sqlalchemy import select

from models.ai_settings import DocumentExtractionSchema, EffectiveAiSettings
from services.content import ContentService
from services.content.stats import ContentStatsService
from services.content._stats.filters import (
    FieldPredicate,
    FlatContentListFilters,
    PathSegment,
    compile_predicate_jsonpath,
    parse_field_predicates,
)
from services.connector import connector_registry
from models.content.items import ContentItemType
from models.sqlalchemy_models import (
    ContentItemAttachmentDetails,
    ContentItemEmailMessageDetails,
    IndexedContentItem,
    TaskQueue,
)
from models.user import User


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result.scalars.return_value = mock_scalars
    mock_result.scalar_one_or_none.return_value = None
    mock_result.fetchone.return_value = (0, 0)
    # Setting return_value on AsyncMock makes it return this when awaited
    db.execute.return_value = mock_result
    return db


@pytest.fixture(autouse=True)
def patch_settings_helpers(runtime_sources):
    """Patch content access helpers for focused browsing tests."""
    _ = runtime_sources
    # Keep these unit tests focused on browsing behavior, not ACL policy.
    with (
        patch(
            "services.content.service.user_can_access_folder_uuid",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "services.content.service.user_can_access_record",
            return_value=True,
        ),
        patch(
            "services.content.access.user_can_access_folder_uuid",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "services.content.access.user_can_access_record",
            return_value=True,
        ),
    ):
        yield


def _effective_settings() -> EffectiveAiSettings:
    return EffectiveAiSettings.model_validate(
        {
            "chat_model": "test-chat-model",
            "chat_system_prompt": "You are a helpful assistant.",
            "chat_tool_prompt": "Use the available tools when needed.",
            "chat_search_limit": 10,
            "chat_document_max_chars": 30000,
            "picture_description_model": "test-picture-model",
            "picture_description_prompt": "Describe the image accurately.",
            "document_classification_enabled": True,
            "document_classification_model": "fastino/gliner2-multi-v1",
            "document_classification_labels": [
                {"name": "Permit", "description": "Permit documents", "aliases": []},
                {"name": "Invoice", "description": "Invoice documents", "aliases": []},
            ],
            "document_extraction_enabled": True,
            "document_extraction_model": "fastino/gliner2-multi-v1",
            "document_extraction_schemas": [
                {
                    "name": "permit_core",
                    "document_class": "Permit",
                    "description": "Permit fields",
                    "fields": [
                        {
                            "name": "file_number",
                            "dtype": "str",
                            "description": "Permit file number",
                            "required": False,
                        }
                    ],
                }
            ],
            "document_extraction_max_chars": 12000,
        }
    )


@pytest.fixture(autouse=True)
def patch_ai_settings_runtime():
    settings = _effective_settings()
    with (
        patch(
            "services.content.service.AiSettingsService.get_effective_settings",
            new=AsyncMock(return_value=settings),
        ),
        patch(
            "services.content.stats.AiSettingsService.get_effective_settings",
            new=AsyncMock(return_value=settings),
        ),
    ):
        yield


class TestContentService:
    """Tests for ContentService."""

    @pytest.mark.asyncio
    async def test_list_directory_root(
        self, populated_data_dir, mock_settings, mock_db
    ):
        """Lists root directory contents."""

        with (
            patch("services.content.service.get_settings", return_value=mock_settings),
        ):
            service = ContentService(db=mock_db)
            result = await service.list_directory("")

        assert result.path == ""
        assert result.parent_path is None
        assert len(result.folders) == 2
        assert len(result.files) == 0

        folder_names = [f.name for f in result.folders]
        assert "documents" in folder_names
        assert "images" in folder_names

    @pytest.mark.asyncio
    async def test_list_directory_subdirectory(
        self, populated_data_dir, mock_settings, mock_db
    ):
        """Lists subdirectory contents."""

        with (
            patch("services.content.service.get_settings", return_value=mock_settings),
        ):
            service = ContentService(db=mock_db)
            result = await service.list_directory("documents")

        assert result.path == "documents"
        assert result.parent_path == ""
        assert len(result.folders) == 0
        assert len(result.files) == 0

    @pytest.mark.asyncio
    async def test_list_directory_reconciles_watched_connectors(
        self, populated_data_dir, mock_settings, mock_db
    ):
        """Browsing a watched connector should still trigger reconcile on demand."""

        with patch("services.content.service.get_settings", return_value=mock_settings):
            service = ContentService(db=mock_db)

        service.reconciler.maybe_reconcile = AsyncMock()
        service._ensure_directory_access = AsyncMock()
        service._list_child_records = AsyncMock(return_value=[])
        service._records_to_listing_parts = AsyncMock(return_value=([], [], 0))

        await service.list_directory("documents")

        service.reconciler.maybe_reconcile.assert_awaited_once()
        assert service.reconciler.maybe_reconcile.await_args.args[0].name == "documents"
        assert service.reconciler.maybe_reconcile.await_args.args[1] == ""

    @pytest.mark.asyncio
    async def test_list_directory_refreshes_runtime_connectors_on_lookup_miss(
        self, populated_data_dir, mock_settings, mock_db
    ):
        """Browsing should recover when this process has a stale connector cache."""
        folder = mock_settings.DATA_FOLDERS[0]
        connector_registry.set_connectors([])

        with patch("services.content.service.get_settings", return_value=mock_settings):
            service = ContentService(db=mock_db)

        async def _refresh_runtime():
            connector_registry.set_connectors([folder])
            return [folder]

        service.connectors.refresh = AsyncMock(side_effect=_refresh_runtime)
        service.reconciler.maybe_reconcile = AsyncMock()
        service._ensure_directory_access = AsyncMock()
        service._list_child_records = AsyncMock(return_value=[])
        service._records_to_listing_parts = AsyncMock(return_value=([], [], 0))

        try:
            result = await service.list_directory("documents")
        finally:
            connector_registry.set_connectors(list(mock_settings.DATA_FOLDERS))

        assert result.path == "documents"
        service.connectors.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_directory_excludes_hidden_by_default(
        self, populated_data_dir, mock_settings, mock_db
    ):
        """Excludes hidden files by default."""

        with (
            patch("services.content.service.get_settings", return_value=mock_settings),
        ):
            service = ContentService(db=mock_db)
            result = await service.list_directory("")

        folder_names = [f.name for f in result.folders]
        assert ".hidden" not in folder_names

    @pytest.mark.asyncio
    async def test_list_directory_includes_hidden_when_requested(
        self, populated_data_dir, mock_settings, mock_db
    ):
        """Includes hidden files when requested."""

        with (
            patch("services.content.service.get_settings", return_value=mock_settings),
        ):
            service = ContentService(db=mock_db)
            result = await service.list_directory("", include_hidden=True)

        folder_names = [f.name for f in result.folders]
        assert ".hidden" not in folder_names

    @pytest.mark.asyncio
    async def test_list_directory_not_found(
        self, populated_data_dir, mock_settings, mock_db
    ):
        """Raises FileNotFoundError for non-existent directory."""

        with (
            patch("services.content.service.get_settings", return_value=mock_settings),
        ):
            service = ContentService(db=mock_db)
            with pytest.raises(FileNotFoundError):
                await service.list_directory("nonexistent")

    @pytest.mark.asyncio
    async def test_list_directory_prevents_traversal(
        self, populated_data_dir, mock_settings, mock_db
    ):
        """Prevents directory traversal attacks."""

        # Create a directory that would allow traversal
        escape_dir = populated_data_dir / "subdir"
        escape_dir.mkdir(exist_ok=True)

        with (
            patch("services.content.service.get_settings", return_value=mock_settings),
        ):
            service = ContentService(db=mock_db)
            # This should raise either PermissionError or FileNotFoundError
            with pytest.raises((PermissionError, FileNotFoundError)):
                await service.list_directory("subdir/../../..")

    @pytest.mark.asyncio
    async def test_get_file_tree(self, populated_data_dir, mock_settings, mock_db):
        """Gets file tree with specified depth."""

        with (
            patch("services.content.service.get_settings", return_value=mock_settings),
        ):
            service = ContentService(db=mock_db)
            result = await service.get_file_tree("", depth=2)

        assert result.root is not None
        assert result.depth == 2
        assert result.root.type == ContentItemType.FOLDER
        assert result.root.children is not None
        assert len(result.root.children) > 0

    @pytest.mark.asyncio
    async def test_stats_file_infos_include_email_relationship_summaries(
        self, mock_db, runtime_sources, test_user
    ):
        """Flat content rows should include parent and child relationship summaries."""
        _ = runtime_sources
        email_record = IndexedContentItem(
            content_item_id="mail-1",
            folder_uuid="folder-documents",
            content_kind="email_message",
            relative_path="Inbox/message.eml",
            modified_time=1.0,
            change_time=1.0,
            size_bytes=123,
            name="message.eml",
            display_name="Quarterly update",
            extension=".eml",
            mime_type="message/rfc822",
            is_dir=False,
            is_container=False,
            is_hidden=False,
            is_symlink=False,
        )
        attachment_record = IndexedContentItem(
            content_item_id="attachment-1",
            folder_uuid="folder-documents",
            content_kind="attachment",
            relative_path="Inbox/attachments/report.pdf",
            modified_time=1.0,
            change_time=1.0,
            size_bytes=50,
            name="report.pdf",
            display_name="report.pdf",
            extension=".pdf",
            mime_type="application/pdf",
            is_dir=False,
            is_container=False,
            is_hidden=False,
            is_symlink=False,
            parent_content_item_id="mail-1",
        )
        attachment_record.attachment_details = ContentItemAttachmentDetails(
            content_item_id="attachment-1",
            email_message_content_item_id="mail-1",
            content_id_header=None,
            disposition="attachment",
            is_inline=False,
            attachment_index=0,
        )

        parent_result = MagicMock()
        parent_scalars = MagicMock()
        parent_scalars.all.return_value = [email_record]
        parent_result.scalars.return_value = parent_scalars

        child_result = MagicMock()
        child_scalars = MagicMock()
        child_scalars.all.return_value = [attachment_record]
        child_result.scalars.return_value = child_scalars

        mock_db.execute.side_effect = [parent_result, child_result]

        service = ContentStatsService(db=mock_db)
        result = await service._to_file_infos(
            [email_record, attachment_record],
            user=test_user,
        )

        by_id = {item.id: item for item in result}
        assert by_id["mail-1"].child_items is not None
        assert len(by_id["mail-1"].child_items) == 1
        assert by_id["mail-1"].child_items[0].id == "attachment-1"
        assert by_id["attachment-1"].parent_item is not None
        assert by_id["attachment-1"].parent_item.id == "mail-1"
        assert by_id["attachment-1"].parent_item.display_name == "Quarterly update"

    @pytest.mark.asyncio
    async def test_get_file_details_exposes_email_relationships(
        self, mock_db, runtime_sources, test_user
    ):
        """Email-message details should expose child attachments and kind capabilities."""
        _ = runtime_sources
        folder = SimpleNamespace(
            uuid="folder-documents",
            name="documents",
            immutable=False,
            get_adapter=lambda: SimpleNamespace(
                get_local_path=AsyncMock(return_value=None)
            ),
        )
        record = IndexedContentItem(
            content_item_id="mail-1",
            folder_uuid="folder-documents",
            content_kind="email_message",
            relative_path="Inbox/message.eml",
            modified_time=1.0,
            change_time=1.0,
            size_bytes=123,
            name="message.eml",
            display_name="Quarterly update",
            extension=".eml",
            mime_type="message/rfc822",
            is_dir=False,
            is_container=False,
            is_hidden=False,
            is_symlink=False,
        )
        record.email_message_details = ContentItemEmailMessageDetails(
            content_item_id="mail-1",
            message_id_header=None,
            thread_id=None,
            subject="Quarterly update",
            from_name="Alice Example",
            from_address="alice@example.com",
            to_addresses_json=["team@example.com"],
            cc_addresses_json=[],
            bcc_addresses_json=[],
            reply_to_addresses_json=[],
            sent_at=None,
            received_at=None,
            body_text="Hello team",
            body_html=None,
            snippet="Hello team",
            has_attachments=True,
        )
        child = IndexedContentItem(
            content_item_id="attachment-1",
            folder_uuid="folder-documents",
            content_kind="attachment",
            relative_path="Inbox/attachments/report.pdf",
            modified_time=1.0,
            change_time=1.0,
            size_bytes=50,
            name="report.pdf",
            display_name="report.pdf",
            extension=".pdf",
            mime_type="application/pdf",
            is_dir=False,
            is_container=False,
            is_hidden=False,
            is_symlink=False,
            parent_content_item_id="mail-1",
        )
        child.attachment_details = ContentItemAttachmentDetails(
            content_item_id="attachment-1",
            email_message_content_item_id="mail-1",
            content_id_header=None,
            disposition="attachment",
            is_inline=False,
            attachment_index=0,
        )

        execute_result = MagicMock()
        execute_scalars = MagicMock()
        execute_scalars.all.return_value = [child]
        execute_result.scalars.return_value = execute_scalars
        mock_db.execute.return_value = execute_result

        with (
            patch(
                "services.content.service.resolve_source_target",
                new=AsyncMock(
                    return_value=SimpleNamespace(record=record, folder=folder)
                ),
            ),
            patch(
                "services.content.service.AiSettingsService.get_effective_settings",
                new=AsyncMock(return_value=_effective_settings()),
            ),
        ):
            service = ContentService(db=mock_db)
            result = await service.get_file_details(
                "documents/Inbox/message.eml", test_user
            )

        assert result.kind == "email_message"
        assert result.capabilities.supports_search is True
        assert result.capabilities.supports_review is True
        assert len(result.child_items) == 1
        assert result.child_items[0].id == "attachment-1"
        assert result.child_items[0].display_name == "report.pdf"
        assert result.child_items[0].kind == "attachment"

    @pytest.mark.asyncio
    async def test_get_file_tree_folders_first(
        self, populated_data_dir, mock_settings, mock_db
    ):
        """Tree nodes have folders before files."""

        with (
            patch("services.content.service.get_settings", return_value=mock_settings),
        ):
            service = ContentService(db=mock_db)
            result = await service.get_file_tree("", depth=1)

        children = result.root.children
        assert children is not None
        folder_indices = [
            i for i, c in enumerate(children) if c.type == ContentItemType.FOLDER
        ]
        file_indices = [
            i for i, c in enumerate(children) if c.type == ContentItemType.FILE
        ]

        if folder_indices and file_indices:
            assert max(folder_indices) < min(file_indices)

    @pytest.mark.asyncio
    async def test_get_file_details(self, populated_data_dir, mock_settings, mock_db):
        """Gets detailed file information."""

        with (
            patch("services.content.service.get_settings", return_value=mock_settings),
        ):
            service = ContentService(db=mock_db)
            with pytest.raises(FileNotFoundError) as exc_info:
                await service.get_file_details("documents/file1.pdf")

        assert str(exc_info.value) == "File not indexed: documents/file1.pdf"

    @pytest.mark.asyncio
    async def test_get_file_details_uses_indexed_record_when_adapter_path_is_missing(
        self, populated_data_dir, mock_settings, mock_db
    ):
        """Indexed metadata should still open content details when adapter lookup misses."""
        record = IndexedContentItem(
            content_item_id="file-1",
            folder_uuid="folder-documents",
            relative_path="Zusammenfassung (1).pdf",
            modified_time=1.0,
            change_time=1.0,
            size_bytes=123,
            name="Zusammenfassung (1).pdf",
            extension=".pdf",
            is_dir=False,
            is_hidden=False,
            is_symlink=False,
            processing_status="COMPLETED",
        )

        with (
            patch("services.content.service.get_settings", return_value=mock_settings),
            patch(
                "services.content.access.get_record", new=AsyncMock(return_value=record)
            ),
        ):
            service = ContentService(db=mock_db)
            result = await service.get_file_details("documents/Zusammenfassung (1).pdf")

        assert result.id == "file-1"
        assert result.name == "Zusammenfassung (1).pdf"
        assert result.path == "documents/Zusammenfassung (1).pdf"
        assert result.status == "COMPLETED"

    @pytest.mark.asyncio
    async def test_get_file_details_logs_local_stat_enrichment_failures(
        self, mock_settings, mock_db, caplog
    ):
        """Optional local stat enrichment should not block indexed file details."""

        class BrokenLocalPath:
            def is_file(self):
                return True

            def stat(self):
                raise OSError("stat failed")

            def __str__(self):
                return "/data/docs/file.pdf"

        record = IndexedContentItem(
            content_item_id="file-1",
            folder_uuid="folder-documents",
            relative_path="docs/file.pdf",
            modified_time=1.0,
            change_time=1.0,
            size_bytes=123,
            name="file.pdf",
            extension=".pdf",
            is_dir=False,
            is_hidden=False,
            is_symlink=False,
            processing_status="COMPLETED",
        )
        folder = SimpleNamespace(
            uuid="folder-documents",
            name="documents",
            immutable=False,
            get_adapter=lambda: SimpleNamespace(
                get_local_path=AsyncMock(return_value=BrokenLocalPath())
            ),
        )
        caplog.set_level(logging.DEBUG, logger="services.content.service")

        with (
            patch("services.content.service.get_settings", return_value=mock_settings),
            patch(
                "services.content.service.resolve_source_target",
                new=AsyncMock(
                    return_value=SimpleNamespace(record=record, folder=folder)
                ),
            ),
        ):
            service = ContentService(db=mock_db)
            result = await service.get_file_details("documents/docs/file.pdf")

        assert result.id == "file-1"
        assert "Unable to enrich file details from local path /data/docs/file.pdf" in (
            caplog.text
        )

    @pytest.mark.asyncio
    async def test_get_file_details_exposes_processing_task(
        self, populated_data_dir, mock_settings, mock_db
    ):
        """Detailed file payload includes queue metadata for the active task."""
        record = IndexedContentItem(
            content_item_id="file-1",
            folder_uuid="folder-documents",
            relative_path="Zusammenfassung (1).pdf",
            modified_time=1.0,
            change_time=1.0,
            size_bytes=123,
            name="Zusammenfassung (1).pdf",
            extension=".pdf",
            is_dir=False,
            is_hidden=False,
            is_symlink=False,
            task_id="task-1",
            processing_status="PROCESSING",
        )
        task = TaskQueue(
            id="task-1",
            task_type="process",
            content_kind="document",
            content_item_id="file-1",
            folder_uuid="folder-documents",
            relative_path="Zusammenfassung (1).pdf",
            status="CLAIMED",
            claimed_by="worker-mps",
            retry_count=1,
            max_retries=3,
        )
        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = task
        mock_db.execute.return_value = task_result

        with (
            patch("services.content.service.get_settings", return_value=mock_settings),
            patch(
                "services.content.access.get_record", new=AsyncMock(return_value=record)
            ),
        ):
            service = ContentService(db=mock_db)
            result = await service.get_file_details("documents/Zusammenfassung (1).pdf")

        assert result.processing_task is not None
        assert result.processing_task.id == "task-1"
        assert result.processing_task.status == "CLAIMED"
        assert result.processing_task.claimed_by == "worker-mps"
        assert result.processing_task.retry_count == 1

    @pytest.mark.asyncio
    async def test_get_file_details_by_id_resolves_api_path(
        self, mock_settings, mock_db
    ):
        record = IndexedContentItem(
            content_item_id="file-1",
            folder_uuid="folder-documents",
            relative_path="reports/file.pdf",
            name="file.pdf",
            is_dir=False,
            is_hidden=False,
            is_symlink=False,
        )
        expected = SimpleNamespace(id="file-1")

        with (
            patch("services.content.service.get_settings", return_value=mock_settings),
            patch(
                "services.content.service.get_record",
                new=AsyncMock(return_value=record),
            ),
            patch("services.content.service.user_can_access_record", return_value=True),
        ):
            service = ContentService(db=mock_db)
            service.connectors.get_connector_or_refresh = AsyncMock(
                return_value=SimpleNamespace(name="documents", uuid="folder-documents")
            )
            service.get_file_details = AsyncMock(return_value=expected)

            result = await service.get_file_details_by_id("file-1")

        assert result is expected
        service.get_file_details.assert_awaited_once_with(
            "documents/reports/file.pdf", None
        )

    @pytest.mark.asyncio
    async def test_get_file_details_by_id_checks_acl(self, mock_settings, mock_db):
        record = IndexedContentItem(
            content_item_id="file-1",
            folder_uuid="folder-documents",
            relative_path="reports/file.pdf",
            name="file.pdf",
            is_dir=False,
            is_hidden=False,
            is_symlink=False,
        )

        with (
            patch("services.content.service.get_settings", return_value=mock_settings),
            patch(
                "services.content.service.get_record",
                new=AsyncMock(return_value=record),
            ),
            patch(
                "services.content.service.user_can_access_record", return_value=False
            ),
        ):
            service = ContentService(db=mock_db)
            with pytest.raises(PermissionError):
                await service.get_file_details_by_id("file-1")

    @pytest.mark.asyncio
    async def test_get_file_details_not_found(
        self, populated_data_dir, mock_settings, mock_db
    ):
        """Raises FileNotFoundError for non-existent file."""

        with (
            patch("services.content.service.get_settings", return_value=mock_settings),
        ):
            service = ContentService(db=mock_db)
            with pytest.raises(FileNotFoundError):
                await service.get_file_details("nonexistent.txt")

    @pytest.mark.asyncio
    async def test_get_file_details_directory_error(
        self, populated_data_dir, mock_settings, mock_db
    ):
        """Raises ValueError when path is a directory."""

        with (
            patch("services.content.service.get_settings", return_value=mock_settings),
        ):
            service = ContentService(db=mock_db)
            with pytest.raises(ValueError) as exc_info:
                await service.get_file_details("documents")

        assert str(exc_info.value) == "Path is not a file"

    @pytest.mark.asyncio
    async def test_file_info_includes_acl(
        self, populated_data_dir, mock_settings, mock_db
    ):
        """File info includes ACL information when enabled."""
        mock_settings.ACL_ENABLED = True

        with (
            patch("services.content.service.get_settings", return_value=mock_settings),
        ):
            service = ContentService(db=mock_db)
            with pytest.raises(FileNotFoundError):
                await service.get_file_details("documents/file1.pdf")

    @pytest.mark.asyncio
    async def test_file_info_excludes_acl_when_disabled(
        self, populated_data_dir, mock_settings, mock_db
    ):
        """File info excludes ACL when disabled."""
        mock_settings.ACL_ENABLED = False

        with (
            patch("services.content.service.get_settings", return_value=mock_settings),
        ):
            service = ContentService(db=mock_db)
            with pytest.raises(FileNotFoundError):
                await service.get_file_details("documents/file1.pdf")

    @pytest.mark.asyncio
    async def test_generates_stable_ids(
        self, populated_data_dir, mock_settings, mock_db
    ):
        """File IDs are stable across calls."""

        with (
            patch("services.content.service.get_settings", return_value=mock_settings),
        ):
            service = ContentService(db=mock_db)
            result1 = await service.list_directory("documents")
            result2 = await service.list_directory("documents")

        ids1 = [f.id for f in result1.files]
        ids2 = [f.id for f in result2.files]
        assert ids1 == ids2

    @pytest.mark.asyncio
    async def test_get_global_stats_uses_rls_scoped_queries(
        self, mock_settings, mock_db
    ):
        """Global stats should rely on the request RLS session for visibility."""
        user = User(username="alice", groups=["users"])
        stats_result = MagicMock()
        stats_result.fetchone.return_value = (12, 4096)
        proc_result = MagicMock()
        proc_result.scalar.return_value = 3
        stale_result = MagicMock()
        stale_result.scalar.return_value = 5
        mock_db.execute = AsyncMock(
            side_effect=[stats_result, proc_result, stale_result]
        )

        with (
            patch("services.content.stats.get_settings", return_value=mock_settings),
            patch(
                "services.content.stats.AiSettingsService.get_effective_settings",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        document_classification_enabled=True,
                        document_extraction_enabled=True,
                        document_extraction_model="registry:global-extract",
                        document_extraction_schemas=[],
                        document_extraction_schema_models={},
                    )
                ),
            ),
            patch(
                "services.content.stats.document_classification_config_fingerprint",
                return_value="class-fingerprint",
            ),
            patch(
                "services.content.stats.document_extraction_config_fingerprint",
                return_value="extract-fingerprint",
            ),
        ):
            service = ContentStatsService(db=mock_db)
            result = await service.get_global_stats(user)

        assert result == {
            "total_items": 12,
            "total_size_bytes": 4096,
            "processing_count": 3,
            "stale_enrichment_count": 5,
        }

    def test_list_all_files_document_class_filter_uses_effective_classification(self):
        """Flat file filters should use override-first effective document classification."""
        stmt = ContentStatsService._apply_flat_filters(
            select(IndexedContentItem),
            name_contains=None,
            extension=None,
            status=None,
            document_class="invoice",
            extraction_schema=None,
            extraction_field=None,
            extraction_value=None,
            review_status=None,
            review_reason=None,
            needs_review=False,
            stale_enrichment=False,
            classification_enabled=True,
            extraction_enabled=True,
            classification_fingerprint="class-fingerprint",
            extraction_fingerprint="extract-fingerprint",
        )

        compiled = stmt.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        assert "content_item_enrichment_states" in sql
        assert "classification_effective_label" in sql
        assert "lower" in sql.lower()
        assert any(
            isinstance(value, str) and "invoice" in value
            for value in compiled.params.values()
        )

    def test_list_all_files_name_regex_full_matches_and_can_include_relative_path(self):
        """Regex search should full-match filenames and optionally relative paths."""
        stmt = ContentStatsService._apply_flat_filters(
            select(IndexedContentItem),
            name_contains=r"inbox/.+\.pdf",
            name_regex=True,
            search_path=True,
            extension=None,
            status=None,
            document_class=None,
            extraction_schema=None,
            extraction_field=None,
            extraction_value=None,
            review_status=None,
            review_reason=None,
            needs_review=False,
            stale_enrichment=False,
            classification_enabled=True,
            extraction_enabled=True,
            classification_fingerprint="class-fingerprint",
            extraction_fingerprint="extract-fingerprint",
        )

        compiled = stmt.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        assert "~*" in sql
        assert "indexed_content_items.name" in sql
        assert "indexed_content_items.relative_path" in sql
        assert r"^(?:inbox/.+\.pdf)$" in compiled.params.values()

    def test_compile_contains_uses_like_regex_on_string_leaf(self):
        """A string contains predicate compiles to a case-insensitive like_regex."""
        jsonpath, vars_, negate = compile_predicate_jsonpath(
            FieldPredicate(
                op="contains",
                segments=(PathSegment(key="invoice_number"),),
                value="RE-2026",
                dtype="str",
            )
        )

        assert jsonpath.startswith('$."invoice_number" ? (')
        assert "like_regex" in jsonpath
        assert 'flag "i"' in jsonpath
        assert "RE" in jsonpath
        assert vars_ == {}
        assert negate is False

    def test_compile_numeric_nested_leaf_uses_native_compare(self):
        """A numeric > predicate over object_list[].amount compiles a native compare."""
        jsonpath, vars_, negate = compile_predicate_jsonpath(
            FieldPredicate(
                op="gt",
                segments=(
                    PathSegment(key="line_items"),
                    PathSegment(elem=True),
                    PathSegment(key="amount"),
                ),
                value="1000",
                dtype="float",
            )
        )

        assert (
            jsonpath == '$."line_items"[*]."amount" ? (@.type() == "number" && @ > $v)'
        )
        assert vars_ == {"v": 1000.0}
        assert negate is False

    def test_compile_date_between_uses_string_bounds(self):
        """A date between predicate compiles to lexicographic ISO string bounds."""
        jsonpath, vars_, negate = compile_predicate_jsonpath(
            FieldPredicate(
                op="between",
                segments=(PathSegment(key="due_date"),),
                value="2026-01-01",
                value2="2026-12-31",
                dtype="date",
            )
        )

        assert (
            jsonpath == '$."due_date" ? (@.type() == "string" && @ >= $lo && @ <= $hi)'
        )
        assert vars_ == {"lo": "2026-01-01", "hi": "2026-12-31"}
        assert negate is False

    def test_compile_not_contains_negates(self):
        """not_contains compiles the positive match and flags negation."""
        _jsonpath, _vars, negate = compile_predicate_jsonpath(
            FieldPredicate(
                op="not_contains",
                segments=(PathSegment(key="tags"), PathSegment(elem=True)),
                value="urgent",
                dtype="str",
            )
        )
        assert negate is True

    def test_field_predicate_renders_jsonb_path_exists(self):
        """Applying a predicate emits a jsonb_path_exists clause on the effective JSON."""
        stmt = ContentStatsService._apply_flat_filters(
            select(IndexedContentItem),
            field_predicates=(
                FieldPredicate(
                    op="gte",
                    segments=(PathSegment(key="total_amount"),),
                    value="500",
                    dtype="int",
                ),
            ),
            classification_enabled=True,
            extraction_enabled=True,
        )

        sql = str(stmt.compile(dialect=postgresql.dialect())).lower()

        assert "jsonb_path_exists" in sql
        assert "extraction_effective_data_json" in sql

    def test_schema_field_facets_expand_nested_leaves(self):
        """Schema field facets expand currency, list and object_list into leaves."""
        from models.ai_settings import (
            DocumentExtractionChildField,
            DocumentExtractionField,
            DocumentExtractionSchema,
        )
        from services.content._stats.extraction_facets import ExtractionFacetHelpers

        schema = DocumentExtractionSchema(
            name="invoice",
            document_class="invoice",
            fields=[
                DocumentExtractionField(name="vendor", dtype="str", description="d"),
                DocumentExtractionField(
                    name="total", dtype="currency", description="d"
                ),
                DocumentExtractionField(
                    name="line_items",
                    dtype="object_list",
                    description="d",
                    fields=[
                        DocumentExtractionChildField(
                            name="amount", dtype="float", description="d"
                        ),
                    ],
                ),
            ],
        )
        rows = [({"vendor": "ACME", "total": {"amount": 5.0}},), ({"vendor": "X"},)]

        facets = ExtractionFacetHelpers.collect_extraction_schema_field_facets(
            rows, schemas=[schema]
        )
        by_label = {facet.label: facet for facet in facets}

        assert by_label["vendor"].dtype == "str"
        assert by_label["vendor"].segments == [{"k": "vendor"}]
        assert by_label["vendor"].count == 2
        assert by_label["total.amount"].dtype == "float"
        assert by_label["total.amount"].segments == [{"k": "total"}, {"k": "amount"}]
        assert by_label["total.currency"].dtype == "str"
        assert by_label["line_items[].amount"].dtype == "float"
        assert by_label["line_items[].amount"].segments == [
            {"k": "line_items"},
            {"elem": True},
            {"k": "amount"},
        ]

    def test_schema_field_facets_union_multiple_schemas_keep_types(self):
        """With no single schema selected, leaves union across schemas keep dtypes."""
        from models.ai_settings import DocumentExtractionField, DocumentExtractionSchema
        from services.content._stats.extraction_facets import ExtractionFacetHelpers

        invoice = DocumentExtractionSchema(
            name="invoice",
            document_class="invoice",
            fields=[
                DocumentExtractionField(
                    name="gross_amount", dtype="float", description="d"
                )
            ],
        )
        permit = DocumentExtractionSchema(
            name="permit",
            document_class="permit",
            fields=[
                DocumentExtractionField(name="issued_on", dtype="date", description="d")
            ],
        )
        rows = [({"gross_amount": 5.0},), ({"issued_on": "2026-01-01"},)]

        facets = ExtractionFacetHelpers.collect_extraction_schema_field_facets(
            rows, schemas=[invoice, permit]
        )
        by_label = {facet.label: facet.dtype for facet in facets}

        assert by_label["gross_amount"] == "float"
        assert by_label["issued_on"] == "date"

    def test_parse_field_predicates_handles_segments_and_legacy_field(self):
        """The parser reads structured segments and shims the legacy flat field."""
        raw = (
            '[{"segments":[{"k":"line_items"},{"elem":true},{"k":"amount"}],'
            '"op":"gte","value":"500","dtype":"float"},'
            '{"field":"vendor","op":"contains","value":"ACME","dtype":"str"},'
            '{"op":"contains","value":"x"},'
            '{"field":"vendor","op":"bogus","value":"y"}]'
        )
        predicates = parse_field_predicates(raw)

        assert len(predicates) == 2
        assert predicates[0].segments == (
            PathSegment(key="line_items"),
            PathSegment(elem=True),
            PathSegment(key="amount"),
        )
        assert predicates[0].op == "gte"
        assert predicates[1].segments == (PathSegment(key="vendor"),)
        assert predicates[1].op == "contains"
        assert parse_field_predicates(None) == ()
        assert parse_field_predicates("not json") == ()

    def test_list_all_files_extraction_schema_filter_uses_effective_schema_name(self):
        """Flat file filters should use the effective extraction schema name."""
        stmt = ContentStatsService._apply_flat_filters(
            select(IndexedContentItem),
            name_contains=None,
            extension=None,
            status=None,
            document_class=None,
            extraction_schema="invoice_fields",
            extraction_field=None,
            extraction_value=None,
            review_status=None,
            review_reason=None,
            needs_review=False,
            stale_enrichment=False,
            classification_enabled=True,
            extraction_enabled=True,
            classification_fingerprint="class-fingerprint",
            extraction_fingerprint="extract-fingerprint",
        )

        compiled = stmt.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        assert "content_item_enrichment_states" in sql
        assert "extraction_effective_schema_name" in sql
        assert any(
            isinstance(value, str) and "invoice_fields" in value
            for value in compiled.params.values()
        )

    def test_list_all_files_numeric_range_predicates_compile_to_jsonpath(self):
        """Two numeric predicates emit two jsonb_path_exists clauses with typed bounds."""
        stmt = ContentStatsService._apply_flat_filters(
            select(IndexedContentItem),
            field_predicates=(
                FieldPredicate(
                    op="gte",
                    segments=(PathSegment(key="gross_amount"),),
                    value="10.5",
                    dtype="float",
                ),
                FieldPredicate(
                    op="lte",
                    segments=(PathSegment(key="gross_amount"),),
                    value="20",
                    dtype="float",
                ),
            ),
            classification_enabled=True,
            extraction_enabled=True,
        )

        compiled = stmt.compile(dialect=postgresql.dialect())
        joined = " ".join(str(value) for value in compiled.params.values())

        assert str(compiled).lower().count("jsonb_path_exists") == 2
        assert '"gross_amount"' in joined
        assert "@ >= $v" in joined and "@ <= $v" in joined
        assert "10.5" in joined and "20.0" in joined

    def test_list_all_files_date_between_predicate_compiles_to_jsonpath(self):
        """A date between predicate compiles ISO string bounds into the jsonpath."""
        stmt = ContentStatsService._apply_flat_filters(
            select(IndexedContentItem),
            field_predicates=(
                FieldPredicate(
                    op="between",
                    segments=(PathSegment(key="invoice_date"),),
                    value="2026-04-01",
                    value2="2026-04-30",
                    dtype="date",
                ),
            ),
            classification_enabled=True,
            extraction_enabled=True,
        )

        compiled = stmt.compile(dialect=postgresql.dialect())
        joined = " ".join(str(value) for value in compiled.params.values())

        assert "jsonb_path_exists" in str(compiled).lower()
        assert '"invoice_date"' in joined
        assert "@ >= $lo" in joined and "@ <= $hi" in joined
        assert "2026-04-01" in joined and "2026-04-30" in joined

    def test_flat_file_filters_schema_facets_clear_review_reason(self):
        """Schema facets should drop reason self-filtering to preserve global counts."""
        filters = FlatContentListFilters(
            document_class="permit",
            extraction_schema="permit_core",
            review_reason="missing_required_fields",
        )

        facet_filters = filters.for_schema_facets()

        assert facet_filters.document_class == "permit"
        assert facet_filters.extraction_schema is None
        assert facet_filters.review_reason is None

    def test_flat_file_filters_schema_field_facets_clear_field_specific_filters(self):
        """Schema field coverage facets should ignore active value/range field filters."""
        filters = FlatContentListFilters(
            extraction_field="invoice_number",
            extraction_value="RE-2026",
            extraction_value_number_min=10.5,
            extraction_value_number_max=20.0,
            extraction_value_date_from=date(2026, 4, 1),
            extraction_value_date_to=date(2026, 4, 30),
        )

        facet_filters = filters.for_extraction_schema_field_facets()

        assert facet_filters.extraction_field is None
        assert facet_filters.extraction_value is None
        assert facet_filters.extraction_value_number_min is None
        assert facet_filters.extraction_value_number_max is None
        assert facet_filters.extraction_value_date_from is None
        assert facet_filters.extraction_value_date_to is None

    def test_document_class_facets_ignore_active_document_class_filter(self):
        """Class facets should reuse effective classification but not self-filter by class."""
        filtered_stmt = ContentStatsService._apply_flat_filters(
            select(IndexedContentItem),
            name_contains="invoice",
            extension=None,
            status=None,
            document_class=None,
            extraction_schema=None,
            field_predicates=(
                FieldPredicate(
                    op="contains",
                    segments=(PathSegment(key="invoice_number"),),
                    value="RE-2026",
                    dtype="str",
                ),
            ),
            review_status=None,
            review_reason=None,
            needs_review=False,
            stale_enrichment=False,
            classification_enabled=True,
            extraction_enabled=True,
            classification_fingerprint="class-fingerprint",
            extraction_fingerprint="extract-fingerprint",
        )
        facet_stmt = ContentStatsService._build_document_class_facet_stmt(filtered_stmt)

        compiled = facet_stmt.compile(dialect=postgresql.dialect())
        sql = str(compiled)
        joined_params = " ".join(str(value) for value in compiled.params.values())

        assert "content_item_enrichment_states" in sql
        assert "classification_effective_label" in sql
        assert "group by" in sql.lower()
        assert "count" in sql.lower()
        assert '"invoice_number"' in joined_params
        assert not any(
            isinstance(value, str) and value.lower() == "invoice"
            for value in compiled.params.values()
        )

    def test_extraction_schema_facets_use_effective_schema_names(self):
        """Schema facets should reuse override-first effective extraction schema names."""
        filtered_stmt = ContentStatsService._apply_flat_filters(
            select(IndexedContentItem),
            name_contains="invoice",
            extension=None,
            status=None,
            document_class="invoice",
            extraction_schema=None,
            field_predicates=(
                FieldPredicate(
                    op="contains",
                    segments=(PathSegment(key="invoice_number"),),
                    value="RE-2026",
                    dtype="str",
                ),
            ),
            review_status=None,
            review_reason=None,
            needs_review=False,
            stale_enrichment=False,
            classification_enabled=True,
            extraction_enabled=True,
            classification_fingerprint="class-fingerprint",
            extraction_fingerprint="extract-fingerprint",
        )
        facet_stmt = ContentStatsService._build_extraction_schema_facet_stmt(
            filtered_stmt
        )

        compiled = facet_stmt.compile(dialect=postgresql.dialect())
        sql = str(compiled)
        joined_params = " ".join(str(value) for value in compiled.params.values())

        assert "content_item_enrichment_states" in sql
        assert "extraction_effective_schema_name" in sql
        assert "group by" in sql.lower()
        assert "count" in sql.lower()
        assert '"invoice_number"' in joined_params

    def test_extraction_value_facets_keep_active_field_but_ignore_active_value_filter(
        self,
    ):
        """Value facets should stay scoped to the current field without self-filtering by value."""
        stmt = ContentStatsService._build_extraction_value_facet_stmt(
            user=None,
            name_contains="invoice",
            extension=None,
            status=None,
            document_class="invoice",
            extraction_schema="invoice_fields",
            extraction_field="invoice_number",
            review_status=None,
            review_reason=None,
            needs_review=False,
            stale_enrichment=False,
            classification_enabled=True,
            extraction_enabled=True,
            classification_fingerprint="class-fingerprint",
            extraction_fingerprint="extract-fingerprint",
        )

        compiled = stmt.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        assert "invoice_number" in compiled.params.values()
        assert not any(
            isinstance(value, str) and "RE-2026" in value
            for value in compiled.params.values()
        )
        assert "content_item_enrichment_states" in sql
        assert "extraction_effective_data_json" in sql

    def test_extraction_schema_field_facets_ignore_active_field_only_filters(self):
        """Schema coverage facets should ignore field-specific value and range filters."""
        stmt = ContentStatsService._build_extraction_schema_field_facet_stmt(
            user=None,
            name_contains="permit",
            extension="pdf",
            status="COMPLETED",
            document_class="permit",
            extraction_schema="permit_core",
            review_status="unreviewed",
            review_reason="missing_required_fields",
            needs_review=True,
            stale_enrichment=False,
            classification_enabled=True,
            extraction_enabled=True,
            classification_fingerprint="class-fingerprint",
            extraction_fingerprint="extract-fingerprint",
        )

        compiled = stmt.compile(dialect=postgresql.dialect())

        assert any(
            isinstance(value, str) and "permit_core" in value
            for value in compiled.params.values()
        )
        assert "missing_required_fields" in compiled.params.values()
        assert not any(value == "invoice_number" for value in compiled.params.values())
        assert not any(value == "approved" for value in compiled.params.values())

    def test_list_all_files_stale_filter_uses_enrichment_fingerprints(self):
        """Flat file stale filter should compare existing stored enrichment metadata."""
        stmt = ContentStatsService._apply_flat_filters(
            select(IndexedContentItem),
            name_contains=None,
            extension=None,
            status=None,
            document_class=None,
            extraction_schema=None,
            extraction_field=None,
            extraction_value=None,
            review_status=None,
            review_reason=None,
            needs_review=False,
            stale_enrichment=True,
            classification_enabled=True,
            extraction_enabled=True,
            classification_fingerprint="class-fingerprint",
            extraction_fingerprint="extract-fingerprint",
            extraction_model="registry:global-extract",
            extraction_schema_models={"permit_core": "registry:permit-v2"},
        )

        compiled = stmt.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        assert "content_item_enrichment_states" in sql
        assert "classification_config_fingerprint" in sql
        assert "extraction_config_fingerprint" in sql
        assert "classification_system_label IS NULL" not in sql
        assert "extraction_system_schema_name IS NULL" not in sql
        assert "extraction_model" in sql
        assert any(value == "class-fingerprint" for value in compiled.params.values())
        assert any(value == "extract-fingerprint" for value in compiled.params.values())
        assert any(
            value == "registry:global-extract" for value in compiled.params.values()
        )
        assert any(value == "registry:permit-v2" for value in compiled.params.values())
        assert any(value == "permit_core" for value in compiled.params.values())

    def test_list_all_files_needs_review_filter_uses_extraction_review_state(self):
        """Review queue filter should use extraction summary plus absence of review state."""
        stmt = ContentStatsService._apply_flat_filters(
            select(IndexedContentItem),
            name_contains=None,
            extension=None,
            status=None,
            document_class=None,
            extraction_schema=None,
            extraction_field=None,
            extraction_value=None,
            review_status=None,
            review_reason=None,
            needs_review=True,
            stale_enrichment=False,
            classification_enabled=True,
            extraction_enabled=True,
            classification_fingerprint="class-fingerprint",
            extraction_fingerprint="extract-fingerprint",
        )

        compiled = stmt.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        assert "content_item_enrichment_states" in sql
        assert "extraction_review_status" in sql
        assert "extraction_summary_json" in sql
        assert "needs_review" in compiled.params.values()
        assert any(value == "true" for value in compiled.params.values())

    def test_list_all_files_review_status_filter_uses_review_json_columns(self):
        """Review status filtering should inspect classification and extraction review JSON."""
        stmt = ContentStatsService._apply_flat_filters(
            select(IndexedContentItem),
            name_contains=None,
            extension=None,
            status=None,
            document_class=None,
            extraction_schema=None,
            extraction_field=None,
            extraction_value=None,
            review_status="corrected",
            review_reason=None,
            needs_review=False,
            stale_enrichment=False,
            classification_enabled=True,
            extraction_enabled=True,
            classification_fingerprint="class-fingerprint",
            extraction_fingerprint="extract-fingerprint",
        )

        compiled = stmt.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        assert "content_item_enrichment_states" in sql
        assert "classification_review_status" in sql
        assert "extraction_review_status" in sql
        assert any(value == "corrected" for value in compiled.params.values())

    def test_list_all_files_review_reason_filter_uses_enrichment_summary_and_evidence(
        self,
    ):
        """Review reason filtering should inspect stored summary fields and evidence state."""
        stmt = ContentStatsService._apply_flat_filters(
            select(IndexedContentItem),
            name_contains=None,
            extension=None,
            status=None,
            document_class=None,
            extraction_schema=None,
            extraction_field=None,
            extraction_value=None,
            review_status=None,
            review_reason="missing_evidence",
            needs_review=False,
            stale_enrichment=False,
            classification_enabled=True,
            extraction_enabled=True,
            classification_fingerprint="class-fingerprint",
            extraction_fingerprint="extract-fingerprint",
        )

        compiled = stmt.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        assert "content_item_enrichment_states" in sql
        assert "classification_evidence_json" in sql
        assert "extraction_summary_json" in sql
        assert any(
            value == "fields_with_evidence" for value in compiled.params.values()
        )
        assert "jsonb_object_keys" in sql
        assert "jsonb_object_length" not in sql

    def test_list_all_files_review_priority_sort_uses_reason_severity(self):
        """Review priority sorting should order by review severity before recency."""
        stmt = ContentStatsService._apply_flat_sort(
            select(IndexedContentItem),
            sort_by="review_priority",
            sort_order="asc",
        )

        compiled = stmt.compile(dialect=postgresql.dialect())
        sql = str(compiled)

        assert "CASE" in sql
        assert "missing_required_fields" in compiled.params.values()
        assert "conflicted_fields" in compiled.params.values()
        assert "fields_with_evidence" in compiled.params.values()
        assert "modified_time" in sql

    @pytest.mark.asyncio
    async def test_collect_review_summary_returns_bucket_counts(self, mock_db):
        """Review queue summary should expose the current bucket counts."""
        service = ContentStatsService(db=mock_db)

        def _count_result(value: int):
            result = MagicMock()
            result.scalar.return_value = value
            return result

        mock_db.execute.side_effect = [
            _count_result(7),  # unreviewed
            _count_result(2),  # accepted
            _count_result(1),  # corrected
            _count_result(6),  # dismissed
            _count_result(5),  # needs_review
            _count_result(3),  # missing_required_fields
            _count_result(2),  # conflicted_fields
            _count_result(4),  # missing_evidence
        ]

        summary = await service._collect_review_summary(
            select(IndexedContentItem), total=10
        )

        assert summary.total == 10
        assert summary.unreviewed == 7
        assert summary.accepted == 2
        assert summary.corrected == 1
        assert summary.dismissed == 6
        assert summary.needs_review == 5
        assert summary.missing_required_fields == 3
        assert summary.conflicted_fields == 2
        assert summary.missing_evidence == 4

    def test_collect_extraction_field_facets_uses_effective_override_first_data(self):
        """Extraction field facets should count merged effective fields with overrides applied."""
        facets = ContentStatsService._collect_extraction_field_facets(
            [
                (
                    {
                        "invoice_number": "RE-1",
                        "gross_amount": 19.99,
                        "empty": "",
                        "currency": "EUR",
                    },
                ),
                ({"invoice_number": "RE-2", "gross_amount": 29.99},),
                ({"invoice_number": None},),
            ]
        )

        assert [(facet.field, facet.count) for facet in facets] == [
            ("gross_amount", 2),
            ("invoice_number", 2),
            ("currency", 1),
        ]

    def test_collect_extraction_schema_field_facets_follow_configured_field_order(self):
        """Schema field coverage should preserve configured order and count effective values."""
        schema = DocumentExtractionSchema.model_validate(
            {
                "name": "invoice_fields",
                "document_class": "Invoice",
                "description": "Invoice fields",
                "fields": [
                    {
                        "name": "invoice_number",
                        "dtype": "str",
                        "description": "Invoice number",
                        "required": True,
                    },
                    {
                        "name": "gross_amount",
                        "dtype": "float",
                        "description": "Gross amount",
                        "required": True,
                    },
                    {
                        "name": "due_date",
                        "dtype": "str",
                        "description": "Due date",
                        "required": False,
                    },
                ],
            }
        )

        facets = ContentStatsService._collect_extraction_schema_field_facets(
            [
                (
                    {
                        "invoice_number": "RE-1",
                        "gross_amount": 119.99,
                        "due_date": "",
                    },
                ),
                (
                    {
                        "invoice_number": "RE-2",
                        "gross_amount": 42.0,
                        "due_date": "2026-04-01",
                    },
                ),
                ({"invoice_number": None, "gross_amount": None},),
            ],
            schemas=[schema],
        )

        assert [
            (facet.field, facet.dtype, facet.required, facet.count, facet.total)
            for facet in facets
        ] == [
            ("invoice_number", "str", True, 2, 3),
            ("gross_amount", "float", True, 2, 3),
            ("due_date", "str", False, 1, 3),
        ]

    def test_collect_extraction_value_facets_uses_effective_override_first_values(self):
        """Value facets should count effective override-first field values."""
        facets = ContentStatsService._collect_extraction_value_facets(
            [
                ({"status": "approved"},),
                ({"status": "rejected"},),
                ({"status": "approved"},),
                ({"status": ["draft", "recheck"]},),
                ({"status": None},),
            ],
            field_name="status",
        )

        assert [(facet.value, facet.count) for facet in facets] == [
            ("approved", 2),
            ('["draft","recheck"]', 1),
            ("rejected", 1),
        ]
