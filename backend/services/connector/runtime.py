"""Read-only runtime connector policy and lookup helpers."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from config import BaseDataConnector, LocalFsDataConnector
from .registry import connector_registry


class ConnectorRuntimeError(RuntimeError):
    """Raised when runtime connector state cannot satisfy a request."""


class ConnectorRuntimeService:
    """Centralizes runtime connector lookup, refresh, and policy filtering."""

    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    async def refresh(self) -> list[BaseDataConnector]:
        """Refresh runtime connectors from DB-backed connector config."""
        if self.db is None:
            return self.all_connectors()

        from .service import DataConnectorService

        return await DataConnectorService(self.db).refresh_runtime_cache()

    def all_connectors(self) -> list[BaseDataConnector]:
        return connector_registry.get_connectors()

    def browsable_connectors(self) -> list[BaseDataConnector]:
        return [
            connector
            for connector in self.all_connectors()
            if getattr(connector, "browsable", True)
        ]

    def get_connector(self, connector_uuid: str) -> BaseDataConnector | None:
        return connector_registry.get_connector_by_uuid(connector_uuid)

    async def get_connector_or_refresh(
        self, connector_uuid: str
    ) -> BaseDataConnector | None:
        connector = self.get_connector(connector_uuid)
        if connector is not None or self.db is None:
            return connector
        await self.refresh()
        return self.get_connector(connector_uuid)

    def get_browsable_connector_by_name(
        self, connector_name: str
    ) -> BaseDataConnector | None:
        for connector in self.browsable_connectors():
            if connector.name == connector_name:
                return connector
        return None

    def get_filesystem_connector_for_path(
        self, full_path: Path
    ) -> LocalFsDataConnector | None:
        resolved = full_path.resolve()
        for connector in self.all_connectors():
            if not isinstance(connector, LocalFsDataConnector):
                continue
            try:
                resolved.relative_to(connector.root_path)
                return connector
            except ValueError:
                continue
        return None

    def connector_name_maps(
        self, *, browsable_only: bool = True
    ) -> tuple[dict[str, str], dict[str, str]]:
        connectors = (
            self.browsable_connectors() if browsable_only else self.all_connectors()
        )
        name_to_uuid = {connector.name: connector.uuid for connector in connectors}
        uuid_to_name = {connector.uuid: connector.name for connector in connectors}
        return name_to_uuid, uuid_to_name
