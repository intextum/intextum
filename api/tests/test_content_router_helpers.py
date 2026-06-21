"""Tests for shared file-router path resolution helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from models.connector_types import LocalFsDataConnector
from models.sqlalchemy_models import IndexedContentItem
from routers.content.helpers import (
    resolve_authorized_source_dir,
    resolve_authorized_source_file,
)
from services.connector import connector_registry


@pytest.mark.asyncio
async def test_resolve_authorized_source_file_uses_indexed_record_when_adapter_misses(
    runtime_sources, mock_settings, test_user
):
    """Indexed file records should satisfy chat source lookups before adapter existence checks."""
    _ = runtime_sources
    file_service = SimpleNamespace(db=AsyncMock())
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
    )

    with (
        patch("services.content.access.get_record", new=AsyncMock(return_value=record)),
        patch("services.content.access.user_can_access_record", return_value=True),
    ):
        folder, rel_path = await resolve_authorized_source_file(
            "documents/Zusammenfassung (1).pdf",
            test_user,
            file_service,
        )

    assert folder.name == "documents"
    assert rel_path == "Zusammenfassung (1).pdf"


@pytest.mark.asyncio
async def test_resolve_authorized_source_file_allows_indexed_non_browsable_connector(
    runtime_sources, test_user
):
    """Non-browsable files stay hidden from browsing but must open in content details."""
    connector_registry.set_connectors(
        [
            *runtime_sources,
            LocalFsDataConnector(
                uuid="system:archive",
                name="Archive Storage",
                path="/tmp/archive",
                browsable=False,
                routing_target=False,
            ),
        ]
    )
    file_service = SimpleNamespace(db=AsyncMock())
    record = IndexedContentItem(
        content_item_id="archive-file-1",
        folder_uuid="system:archive",
        relative_path="uploads/report.pdf",
        modified_time=1.0,
        change_time=1.0,
        size_bytes=123,
        name="report.pdf",
        extension=".pdf",
        is_dir=False,
        is_hidden=False,
        is_symlink=False,
    )

    with (
        patch("services.content.access.get_record", new=AsyncMock(return_value=record)),
        patch("services.content.access.user_can_access_record", return_value=True),
        patch(
            "services.content.access.ConnectorRuntimeService.refresh",
            new=AsyncMock(return_value=connector_registry.get_connectors()),
        ),
    ):
        folder, rel_path = await resolve_authorized_source_file(
            "Archive Storage/uploads/report.pdf",
            test_user,
            file_service,
        )

    assert folder.uuid == "system:archive"
    assert rel_path == "uploads/report.pdf"


@pytest.mark.asyncio
async def test_resolve_authorized_source_file_rejects_directory_records(
    runtime_sources, mock_settings, test_user
):
    """Directory records should still be rejected on file-only source routes."""
    _ = runtime_sources
    file_service = SimpleNamespace(db=AsyncMock())
    record = IndexedContentItem(
        content_item_id="dir-1",
        folder_uuid="folder-documents",
        relative_path="reports",
        modified_time=1.0,
        change_time=1.0,
        size_bytes=0,
        name="reports",
        is_dir=True,
        is_hidden=False,
        is_symlink=False,
    )

    with (
        patch("services.content.access.get_record", new=AsyncMock(return_value=record)),
        patch("services.content.access.user_can_access_record", return_value=True),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await resolve_authorized_source_file(
                "documents/reports", test_user, file_service
            )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Path is not a file"


@pytest.mark.asyncio
async def test_resolve_authorized_source_file_conceals_inaccessible_indexed_records(
    runtime_sources, mock_settings, test_user
):
    """Unauthorized indexed paths should look missing instead of leaking file type/existence."""
    _ = runtime_sources
    file_service = SimpleNamespace(db=AsyncMock())
    record = IndexedContentItem(
        content_item_id="dir-1",
        folder_uuid="folder-documents",
        relative_path="reports",
        modified_time=1.0,
        change_time=1.0,
        size_bytes=0,
        name="reports",
        is_dir=True,
        is_hidden=False,
        is_symlink=False,
    )

    with (
        patch("services.content.access.get_record", new=AsyncMock(return_value=record)),
        patch("services.content.access.user_can_access_record", return_value=False),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await resolve_authorized_source_file(
                "documents/reports",
                test_user,
                file_service,
            )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "File not found"


@pytest.mark.asyncio
async def test_resolve_authorized_source_file_conceals_inaccessible_unindexed_content_items(
    populated_data_dir, runtime_sources, mock_settings, test_user
):
    """Unauthorized live files should also collapse to the same 404 response."""
    _ = populated_data_dir, runtime_sources
    file_service = SimpleNamespace(db=AsyncMock())

    with (
        patch("services.content.access.get_record", new=AsyncMock(return_value=None)),
        patch(
            "services.content.access.user_can_access_folder_uuid",
            new=AsyncMock(return_value=False),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await resolve_authorized_source_file(
                "documents/file1.pdf",
                test_user,
                file_service,
            )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "File not found"


@pytest.mark.asyncio
async def test_resolve_authorized_source_dir_uses_indexed_record_when_adapter_misses(
    runtime_sources, mock_settings, test_user
):
    """Indexed directory records should satisfy directory routes before adapter checks."""
    _ = runtime_sources
    file_service = SimpleNamespace(db=AsyncMock())
    record = IndexedContentItem(
        content_item_id="dir-1",
        folder_uuid="folder-documents",
        relative_path="reports",
        modified_time=1.0,
        change_time=1.0,
        size_bytes=0,
        name="reports",
        is_dir=True,
        is_hidden=False,
        is_symlink=False,
    )

    with (
        patch("services.content.access.get_record", new=AsyncMock(return_value=record)),
        patch("services.content.access.user_can_access_record", return_value=True),
    ):
        folder, rel_path = await resolve_authorized_source_dir(
            "documents/reports",
            test_user,
            file_service,
        )

    assert folder.name == "documents"
    assert rel_path == "reports"


@pytest.mark.asyncio
async def test_resolve_authorized_source_file_refreshes_runtime_connectors_on_lookup_miss(
    populated_data_dir, runtime_sources, test_user
):
    """Path resolution should refresh connector runtime state before failing."""
    _ = populated_data_dir
    folder = runtime_sources[0]
    connector_registry.set_connectors([])
    file_service = SimpleNamespace(db=AsyncMock())

    async def _refresh_runtime():
        connector_registry.set_connectors([folder])
        return [folder]

    with (
        patch("services.content.access.get_record", new=AsyncMock(return_value=None)),
        patch(
            "services.content.access.user_can_access_folder_uuid",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "services.content.access.ConnectorRuntimeService.refresh",
            new=AsyncMock(side_effect=_refresh_runtime),
        ) as refresh_runtime,
    ):
        try:
            resolved_folder, rel_path = await resolve_authorized_source_file(
                "documents/file1.pdf",
                test_user,
                file_service,
            )
        finally:
            connector_registry.set_connectors(list(runtime_sources))

    assert resolved_folder.name == "documents"
    assert rel_path == "file1.pdf"
    refresh_runtime.assert_awaited_once()
