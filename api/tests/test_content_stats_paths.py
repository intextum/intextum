"""Focused tests for flat file path helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.future import select

from models.sqlalchemy_models import IndexedContentItem
from services.content._stats.filters import FlatContentListFilters
from services.content._stats.paths import FlatContentPathNavigator


def _scalars_result(rows):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    return result


def _build_row(content_item_id: str, folder_uuid: str, relative_path: str):
    return IndexedContentItem(
        content_item_id=content_item_id,
        folder_uuid=folder_uuid,
        relative_path=relative_path,
        modified_time=1.0,
        change_time=1.0,
        size_bytes=10,
        name=relative_path,
        extension=".pdf",
        is_dir=False,
        is_hidden=False,
        is_symlink=False,
    )


def _build_service():
    service = MagicMock()
    service.db = MagicMock()
    service._flat_file_base_stmt.return_value = select(IndexedContentItem)
    service._apply_flat_filters.side_effect = lambda stmt, *, filters: stmt
    service._apply_flat_sort.side_effect = lambda stmt, *, sort_by, sort_order: stmt
    return service


@pytest.mark.asyncio
async def test_list_matching_paths_returns_folder_prefixed_paths_and_skips_missing_folders():
    """Path navigation should prefix folder names and ignore unmapped folders."""
    service = _build_service()
    service.db.execute = AsyncMock(
        return_value=_scalars_result(
            [
                _build_row("1", "folder-docs", "a.pdf"),
                _build_row("2", "missing-folder", "b.pdf"),
                _build_row("3", "folder-docs", "nested/c.pdf"),
            ]
        )
    )

    navigator = FlatContentPathNavigator(
        service=service,
        user=None,
        flat_filters=FlatContentListFilters(),
        folder_resolver=lambda folder_uuid: (
            SimpleNamespace(name="documents") if folder_uuid == "folder-docs" else None
        ),
    )

    paths = await navigator.list_matching_paths()

    assert paths == ["documents/a.pdf", "documents/nested/c.pdf"]
