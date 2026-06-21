from unittest.mock import patch

import pytest
from pydantic import ValidationError

from models.connector_types import LocalFsDataConnector
from services.connector import connector_registry
from services.connector import ConnectorRuntimeService


def test_local_fs_force_polling_disabled_when_watch_disabled():
    source = LocalFsDataConnector(
        uuid="source-1",
        name="source-1",
        path="/tmp/source-1",
        watch=False,
        force_polling=True,
    )

    assert source.force_polling is False


def test_local_fs_rejects_invalid_poll_interval():
    with pytest.raises(ValidationError):
        LocalFsDataConnector(
            uuid="source-1",
            name="source-1",
            path="/tmp/source-1",
            poll_interval_seconds=0,
        )


def test_local_fs_db_payload_contains_renamed_processing_flag():
    source = LocalFsDataConnector(
        uuid="source-2",
        name="source-2",
        path="/tmp/source-2",
        auto_process_new=False,
        poll_interval_seconds=45,
    )

    payload = source.to_db_payload()

    assert payload["auto_process_new"] is False
    assert payload["poll_interval_seconds"] == 45
    assert "process" not in payload
    assert "system_managed" not in payload


def test_connector_runtime_filters_non_browsable_system_connectors():
    system = LocalFsDataConnector(
        uuid="system:archive",
        name="System Archive",
        path="/tmp/system",
        system_managed=True,
        browsable=False,
    )
    writable = LocalFsDataConnector(
        uuid="target",
        name="Target",
        path="/tmp/target",
    )
    immutable = LocalFsDataConnector(
        uuid="archive",
        name="Archive",
        path="/tmp/archive",
        immutable=True,
    )
    connector_registry.set_connectors([system, writable, immutable])

    runtime = ConnectorRuntimeService()

    assert [connector.uuid for connector in runtime.browsable_connectors()] == [
        "target",
        "archive",
    ]


@pytest.mark.asyncio
async def test_connector_runtime_refreshes_once_on_lookup_miss(monkeypatch):
    late_connector = LocalFsDataConnector(
        uuid="late",
        name="Late",
        path="/tmp/late",
    )
    refresh_count = 0
    connector_registry.clear()

    async def _refresh_runtime_cache(_service):
        nonlocal refresh_count
        refresh_count += 1
        connector_registry.set_connectors([late_connector])
        return [late_connector]

    monkeypatch.setattr(
        "services.connector.DataConnectorService.refresh_runtime_cache",
        _refresh_runtime_cache,
    )

    runtime = ConnectorRuntimeService(db=object())

    assert await runtime.get_connector_or_refresh("late") is late_connector
    assert refresh_count == 1


def test_smb_notify_requires_server_and_share():
    with pytest.raises(ValidationError, match="smb_server and smb_share are required"):
        LocalFsDataConnector(
            uuid="s1",
            name="s1",
            path="/mnt/share",
            watcher_type="smb_notify",
        )

    with pytest.raises(ValidationError, match="smb_server and smb_share are required"):
        LocalFsDataConnector(
            uuid="s1",
            name="s1",
            path="/mnt/share",
            watcher_type="smb_notify",
            smb_server="fileserver",
        )


def test_smb_notify_forces_polling_false():
    source = LocalFsDataConnector(
        uuid="s1",
        name="s1",
        path="/mnt/share",
        watch=True,
        force_polling=True,
        watcher_type="smb_notify",
        smb_server="fileserver",
        smb_share="docs",
    )
    assert source.force_polling is False


def test_smb_notify_valid_config():
    source = LocalFsDataConnector(
        uuid="s1",
        name="s1",
        path="/mnt/share",
        watch=True,
        watcher_type="smb_notify",
        smb_server="fileserver",
        smb_share="docs",
        smb_port=4455,
        smb_username="admin",
        smb_password="secret",
        smb_domain="CORP",
    )
    assert source.smb_server == "fileserver"
    assert source.smb_share == "docs"
    assert source.smb_port == 4455
    assert source.smb_domain == "CORP"


def test_db_payload_includes_smb_fields():
    source = LocalFsDataConnector(
        uuid="s1",
        name="s1",
        path="/mnt/share",
        watcher_type="auto",
        smb_server=None,
    )
    payload = source.to_db_payload()
    assert payload["watcher_type"] == "auto"
    assert payload["smb_server"] is None
    assert payload["smb_port"] == 445
    assert payload["smb_password"] is None


def test_db_payload_encrypts_smb_password():
    with patch("services.crypto.encrypt_value", return_value="encrypted_secret"):
        source = LocalFsDataConnector(
            uuid="s1",
            name="s1",
            path="/mnt/share",
            watcher_type="smb_notify",
            smb_server="fs",
            smb_share="docs",
            smb_password="secret",
        )
        payload = source.to_db_payload()
        assert payload["smb_password"] == "encrypted_secret"
