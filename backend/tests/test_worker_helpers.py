"""Tests for worker connector boundary helpers."""

from unittest.mock import AsyncMock

import pytest

from models.connector_types import LocalFsDataConnector
from routers.worker.helpers import get_folder, list_worker_folders
from services.connector import connector_registry

SYSTEM_CONNECTOR_UUID = "system:archive"


@pytest.mark.asyncio
async def test_list_worker_folders_excludes_non_browsable_system_connectors(
    monkeypatch,
):
    system = LocalFsDataConnector(
        uuid=SYSTEM_CONNECTOR_UUID,
        name="System Archive",
        path="/tmp/archive",
        browsable=False,
        system_managed=True,
    )
    documents = LocalFsDataConnector(
        uuid="documents",
        name="Documents",
        path="/tmp/documents",
    )
    connector_registry.set_connectors([system, documents])

    refresh = AsyncMock(return_value=[system, documents])
    monkeypatch.setattr(
        "services.connector.DataConnectorService.refresh_runtime_cache", refresh
    )

    folders = await list_worker_folders(db=object())

    assert [folder.uuid for folder in folders] == ["documents"]


@pytest.mark.asyncio
async def test_get_folder_can_resolve_non_browsable_system_connector_for_tasks():
    system = LocalFsDataConnector(
        uuid=SYSTEM_CONNECTOR_UUID,
        name="System Archive",
        path="/tmp/archive",
        browsable=False,
        system_managed=True,
    )
    connector_registry.set_connectors([system])

    folder = await get_folder(SYSTEM_CONNECTOR_UUID)

    assert folder is system
