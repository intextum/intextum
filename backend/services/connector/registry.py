"""Runtime registry for configured data connectors."""

from __future__ import annotations

from models.connector_types import BaseDataConnector


class DataConnectorRegistry:
    """Holds the current in-process runtime view of configured connectors."""

    def __init__(self) -> None:
        self._connectors: tuple[BaseDataConnector, ...] = ()

    def clear(self) -> None:
        self._connectors = ()

    def set_connectors(self, connectors: list[BaseDataConnector]) -> None:
        self._connectors = tuple(connectors)

    def get_connectors(self) -> list[BaseDataConnector]:
        return list(self._connectors)

    def _find_connector(
        self, *, uuid: str | None = None, name: str | None = None
    ) -> BaseDataConnector | None:
        for connector in self._connectors:
            if uuid is not None and connector.uuid == uuid:
                return connector
            if name is not None and connector.name == name:
                return connector
        return None

    def get_connector_by_uuid(self, connector_uuid: str) -> BaseDataConnector | None:
        return self._find_connector(uuid=connector_uuid)

    def get_connector_by_name(self, name: str) -> BaseDataConnector | None:
        return self._find_connector(name=name)


connector_registry = DataConnectorRegistry()

__all__ = ["DataConnectorRegistry", "connector_registry"]
