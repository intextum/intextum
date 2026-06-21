"""Data connector CRUD service with runtime registry refresh support."""

import asyncio
import hashlib
import logging
import shutil
from pathlib import Path

from sqlalchemy import delete as sql_delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from config import get_settings
from models.connector_types import (
    BaseDataConnector,
    DataConnectorTypeDefinition,
    connector_from_payload,
    list_connector_type_definitions,
    normalize_connector_type,
)
from models.sqlalchemy_models import (
    DataSource,
    IndexedContentItem,
    Permission,
    TaskQueue,
)
from .registry import connector_registry
from services.crypto import decrypt_value

logger = logging.getLogger(__name__)

_ENCRYPTED_FIELDS: dict[str, list[str]] = {
    "local_fs": ["smb_password"],
    "s3": ["secret_key"],
}

_LOCAL_FS_COLUMNS: list[str] = [
    "path",
    "force_polling",
    "watcher_type",
    "smb_server",
    "smb_share",
    "smb_port",
    "smb_username",
    "smb_password",
    "smb_domain",
]

_S3_COLUMNS: list[str] = [
    "endpoint_url",
    "bucket",
    "s3_prefix",
    "access_key",
    "secret_key",
    "region",
]

_TYPE_SPECIFIC_COLUMNS: list[str] = _LOCAL_FS_COLUMNS + _S3_COLUMNS

_DB_CONNECTOR_COLUMNS: tuple[str, ...] = (
    "uuid",
    "name",
    "source_type",
    "watch",
    "initial_scan",
    "auto_process_new",
    "immutable",
    "poll_interval_seconds",
    *_TYPE_SPECIFIC_COLUMNS,
)


class DataConnectorService:
    """Manages data connectors and refreshes the in-process runtime registry."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @classmethod
    def list_connector_types(cls) -> list[DataConnectorTypeDefinition]:
        """List connector-type metadata for admin UI/forms."""
        return list_connector_type_definitions()

    @staticmethod
    def _accepted_fields_for_connector_type(connector_type: str) -> set[str]:
        from models.connector_types import _CONNECTOR_REGISTRY

        model_cls = _CONNECTOR_REGISTRY.get(connector_type)
        return set(model_cls.model_fields) if model_cls else set()

    @staticmethod
    def _decrypt_column_value(
        value: object,
        *,
        column: str,
        encrypted_columns: set[str],
    ) -> object:
        if value is not None and column in encrypted_columns:
            if not isinstance(value, str):
                raise ValueError(f"Encrypted field '{column}' must be a string")
            try:
                return decrypt_value(value)
            except ValueError as exc:
                raise ValueError(
                    f"Failed to load encrypted field '{column}': {exc}"
                ) from exc
        return value

    @classmethod
    def _to_runtime_connector(cls, row: DataSource) -> BaseDataConnector:
        connector_type = normalize_connector_type(str(row.source_type))
        encrypted = set(_ENCRYPTED_FIELDS.get(connector_type, []))
        accepted = cls._accepted_fields_for_connector_type(connector_type)

        payload: dict[str, object] = {}
        for col in _DB_CONNECTOR_COLUMNS:
            if accepted and col not in accepted and col != "source_type":
                continue
            value = cls._decrypt_column_value(
                getattr(row, col, None),
                column=col,
                encrypted_columns=encrypted,
            )
            if value is not None:
                payload[col] = value

        payload["connector_type"] = connector_type
        payload.pop("source_type", None)
        return connector_from_payload(payload)

    @classmethod
    def _build_runtime_connector(cls, fields: dict[str, object]) -> BaseDataConnector:
        """Validate and build a runtime connector from arbitrary fields."""
        data = {k: v for k, v in fields.items() if v is not None}
        raw_connector_type = data.get("connector_type") or data.get("source_type")
        if raw_connector_type is not None and not isinstance(raw_connector_type, str):
            raise ValueError("connector_type must be a string")
        connector_type = normalize_connector_type(raw_connector_type)
        data["connector_type"] = connector_type
        data.pop("source_type", None)

        accepted = cls._accepted_fields_for_connector_type(connector_type)
        if accepted:
            data = {k: v for k, v in data.items() if k in accepted}
            data["connector_type"] = connector_type

        return connector_from_payload(data)

    @classmethod
    def _runtime_connectors_from_rows(
        cls, rows: list[DataSource]
    ) -> list[BaseDataConnector]:
        return [cls._to_runtime_connector(row) for row in rows]

    @classmethod
    def _merged_update_fields(
        cls,
        row: DataSource,
        updates: dict[str, object],
        *,
        connector_type: str,
    ) -> dict[str, object]:
        encrypted = set(
            _ENCRYPTED_FIELDS.get(normalize_connector_type(row.source_type), [])
        )
        merged: dict[str, object] = {"uuid": row.uuid, "connector_type": connector_type}
        for col in _DB_CONNECTOR_COLUMNS:
            if col in {"uuid", "source_type"}:
                continue
            if col in updates and updates[col] is not None:
                merged[col] = updates[col]
                continue
            value = cls._decrypt_column_value(
                getattr(row, col, None),
                column=col,
                encrypted_columns=encrypted,
            )
            if value is not None:
                merged[col] = value
        return merged

    async def _delete_connector_related_rows(self, connector_uuid: str) -> None:
        await self.db.execute(
            sql_delete(TaskQueue).where(TaskQueue.folder_uuid == connector_uuid)
        )
        await self.db.execute(
            sql_delete(Permission).where(Permission.folder_uuid == connector_uuid)
        )
        await self.db.execute(
            sql_delete(IndexedContentItem).where(
                IndexedContentItem.folder_uuid == connector_uuid
            )
        )

    async def _list_rows(self) -> list[DataSource]:
        result = await self.db.execute(select(DataSource).order_by(DataSource.name))
        return list(result.scalars().all())

    async def _name_exists(self, name: str, exclude_uuid: str | None = None) -> bool:
        stmt = select(func.count(DataSource.uuid)).where(DataSource.name == name)
        if exclude_uuid:
            stmt = stmt.where(DataSource.uuid != exclude_uuid)
        result = await self.db.execute(stmt)
        return bool(result.scalar() or 0)

    async def _count_folder_references(
        self, connector_uuid: str, model, id_column
    ) -> int:
        result = await self.db.execute(
            select(func.count(id_column)).where(model.folder_uuid == connector_uuid)
        )
        return int(result.scalar() or 0)

    async def _persist_connector_row(self, row: DataSource) -> DataSource:
        await self.db.commit()
        await self.db.refresh(row)
        await self.refresh_runtime_cache()
        return row

    async def _validate_connector_name(
        self,
        name: object,
        *,
        current_name: str | None = None,
        exclude_uuid: str | None = None,
    ) -> str:
        def _name_error() -> str:
            return (
                "name is required" if current_name is None else "name cannot be empty"
            )

        if not isinstance(name, str):
            raise ValueError(_name_error())
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError(_name_error())
        if normalized_name != current_name and await self._name_exists(
            normalized_name,
            exclude_uuid=exclude_uuid,
        ):
            raise ValueError("connector name already exists")
        return normalized_name

    async def refresh_runtime_cache(self) -> list[BaseDataConnector]:
        rows = await self._list_rows()
        connectors = self._runtime_connectors_from_rows(rows)
        connector_registry.set_connectors(connectors)
        return connectors

    async def list_connectors(self) -> list[DataSource]:
        rows = await self._list_rows()
        connector_registry.set_connectors(self._runtime_connectors_from_rows(rows))
        return rows

    async def get_connector(self, connector_uuid: str) -> DataSource | None:
        result = await self.db.execute(
            select(DataSource).where(DataSource.uuid == connector_uuid)
        )
        return result.scalar_one_or_none()

    async def create_connector(
        self, *, uuid: str | None = None, **fields
    ) -> DataSource:
        """Create a new data connector."""
        connector_name = await self._validate_connector_name(fields.get("name"))
        fields["name"] = connector_name

        connector_uuid = (
            uuid or hashlib.sha256(connector_name.encode()).hexdigest()[:12]
        ).strip()
        fields["uuid"] = connector_uuid

        existing = await self.get_connector(connector_uuid)
        if existing is not None:
            raise ValueError("connector uuid already exists")

        runtime_connector = self._build_runtime_connector(fields)
        row = DataSource(**runtime_connector.to_db_payload())
        self.db.add(row)
        return await self._persist_connector_row(row)

    async def update_connector(
        self, connector_uuid: str, **fields
    ) -> DataSource | None:
        """Update an existing data connector."""
        row = await self.get_connector(connector_uuid)
        if row is None:
            return None

        connector_type = normalize_connector_type(
            fields.get("connector_type") or fields.get("source_type") or row.source_type
        )
        merged = self._merged_update_fields(row, fields, connector_type=connector_type)

        candidate_name = await self._validate_connector_name(
            merged.get("name", row.name),
            current_name=row.name,
            exclude_uuid=connector_uuid,
        )
        merged["name"] = candidate_name

        runtime_connector = self._build_runtime_connector(merged)
        payload = runtime_connector.to_db_payload()
        for key, value in payload.items():
            if hasattr(row, key):
                setattr(row, key, value)

        return await self._persist_connector_row(row)

    @staticmethod
    def _cleanup_extracted_data(file_ids: list[str]) -> None:
        """Best-effort cleanup of extracted artifacts for removed files."""
        settings = get_settings()
        extracted_root = Path(settings.EXTRACTED_DATA_DIR)
        for content_item_id in file_ids:
            shutil.rmtree(extracted_root / content_item_id, ignore_errors=True)

    async def delete_connector(
        self, connector_uuid: str, *, force: bool = False
    ) -> bool:
        row = await self.get_connector(connector_uuid)
        if row is None:
            return False

        extracted_file_ids: list[str] = []
        if force:
            file_id_result = await self.db.execute(
                select(IndexedContentItem.content_item_id).where(
                    IndexedContentItem.folder_uuid == connector_uuid
                )
            )
            extracted_file_ids = list(file_id_result.scalars().all())

            await self._delete_connector_related_rows(connector_uuid)
        else:
            indexed_count = await self._count_folder_references(
                connector_uuid, IndexedContentItem, IndexedContentItem.content_item_id
            )
            task_count = await self._count_folder_references(
                connector_uuid, TaskQueue, TaskQueue.id
            )
            perm_count = await self._count_folder_references(
                connector_uuid, Permission, Permission.id
            )

            if indexed_count or task_count or perm_count:
                raise ValueError(
                    "cannot delete connector with existing indexed files, tasks, or permissions"
                )

        await self.db.delete(row)
        await self.db.commit()
        await self.refresh_runtime_cache()

        if force and extracted_file_ids:
            try:
                await asyncio.to_thread(
                    self._cleanup_extracted_data,
                    extracted_file_ids,
                )
            except Exception:
                logger.exception(
                    "Failed to cleanup extracted artifacts for deleted connector %s",
                    connector_uuid,
                )

        return True
