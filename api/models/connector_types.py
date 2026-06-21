"""Runtime connector-definition models for configurable data connectors."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar, Dict, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from services.adapters.base import DataConnectorAdapter

from pydantic import BaseModel, Field, field_validator, model_validator


class DataConnectorFieldDefinition(BaseModel):
    """UI field metadata for a connector type."""

    key: str
    label: str
    description: str = ""
    required: bool = False
    input_type: str = "text"
    placeholder: str | None = None


class DataConnectorTypeDefinition(BaseModel):
    """Type-level metadata for connector creation/edit UIs."""

    connector_type: str
    label: str
    description: str
    fields: list[DataConnectorFieldDefinition] = Field(default_factory=list)


class BaseDataConnector(BaseModel):
    """Base runtime connector config shared by all connector kinds."""

    uuid: str = ""
    name: str
    connector_type: str
    immutable: bool = False
    system_managed: bool = False
    browsable: bool = True
    routing_target: bool = True

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        candidate = value.strip()
        if not candidate:
            raise ValueError("name is required")
        return candidate

    @property
    def is_filesystem_source(self) -> bool:
        """Whether this connector can be resolved to a local filesystem path."""
        return False

    @classmethod
    def type_definition(cls) -> DataConnectorTypeDefinition:
        """Return connector-type metadata for UI consumers."""
        raise NotImplementedError

    def to_db_payload(self) -> dict[str, Any]:
        """Convert runtime model into a DB row payload."""
        raise NotImplementedError

    def get_adapter(self) -> "DataConnectorAdapter":
        """Return a storage adapter for this connector.

        Subclasses must override to return the appropriate adapter.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement get_adapter()"
        )


class LocalFsDataConnector(BaseDataConnector):
    """Local filesystem connector configuration."""

    connector_type: Literal["local_fs"] = "local_fs"
    path: str
    watch: bool = False
    initial_scan: bool = True
    auto_process_new: bool = True
    force_polling: bool = False
    poll_interval_seconds: int = Field(default=30, ge=1)

    # SMB CHANGE_NOTIFY watcher fields
    watcher_type: Literal["auto", "smb_notify"] = "auto"
    smb_server: str | None = None
    smb_share: str | None = None
    smb_port: int = 445
    smb_username: str | None = None
    smb_password: str | None = None
    smb_domain: str | None = None

    _TYPE_DEFINITION: ClassVar[DataConnectorTypeDefinition] = (
        DataConnectorTypeDefinition(
            connector_type="local_fs",
            label="Local Filesystem",
            description="Read files from a local directory on the backend host.",
            fields=[
                DataConnectorFieldDefinition(
                    key="path",
                    label="Path",
                    description="Absolute path to the directory to index.",
                    required=True,
                    input_type="text",
                    placeholder="/data/documents",
                ),
                DataConnectorFieldDefinition(
                    key="watcher_type",
                    label="Watcher Type",
                    description="Change detection backend: 'auto' (inotify/polling) or 'smb_notify' (SMB CHANGE_NOTIFY).",
                    input_type="text",
                ),
                DataConnectorFieldDefinition(
                    key="smb_server",
                    label="SMB Server",
                    description="SMB server hostname or IP (required for smb_notify).",
                    input_type="text",
                ),
                DataConnectorFieldDefinition(
                    key="smb_share",
                    label="SMB Share",
                    description="SMB share name (required for smb_notify).",
                    input_type="text",
                ),
                DataConnectorFieldDefinition(
                    key="smb_port",
                    label="SMB Port",
                    description="SMB port (default 445).",
                    input_type="text",
                ),
                DataConnectorFieldDefinition(
                    key="smb_username",
                    label="SMB Username",
                    description="SMB authentication username.",
                    input_type="text",
                ),
                DataConnectorFieldDefinition(
                    key="smb_password",
                    label="SMB Password",
                    description="SMB authentication password (stored encrypted).",
                    input_type="password",
                ),
                DataConnectorFieldDefinition(
                    key="smb_domain",
                    label="SMB Domain",
                    description="SMB/AD domain for authentication.",
                    input_type="text",
                ),
            ],
        )
    )

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        candidate = value.strip()
        if not candidate:
            raise ValueError("path is required")
        return candidate

    @model_validator(mode="after")
    def _normalize_watch_settings(self) -> "LocalFsDataConnector":
        if not self.watch:
            self.force_polling = False
        if self.watcher_type == "smb_notify":
            if not self.smb_server or not self.smb_share:
                raise ValueError(
                    "smb_server and smb_share are required when watcher_type is 'smb_notify'"
                )
            self.force_polling = False
        return self

    @property
    def is_filesystem_source(self) -> bool:
        return True

    @property
    def root_path(self) -> Path:
        return Path(self.path).resolve()

    @classmethod
    def type_definition(cls) -> DataConnectorTypeDefinition:
        return cls._TYPE_DEFINITION

    def get_adapter(self) -> "DataConnectorAdapter":
        from services.adapters.local_fs import LocalFsAdapter

        return LocalFsAdapter(self)

    @staticmethod
    def _encrypt_password(password: str) -> str:
        from services.crypto import encrypt_value

        return encrypt_value(password)

    def to_db_payload(self) -> dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "source_type": self.connector_type,
            "path": self.path,
            "immutable": self.immutable,
            "watch": self.watch,
            "initial_scan": self.initial_scan,
            "auto_process_new": self.auto_process_new,
            "force_polling": self.force_polling,
            "poll_interval_seconds": self.poll_interval_seconds,
            "watcher_type": self.watcher_type,
            "smb_server": self.smb_server,
            "smb_share": self.smb_share,
            "smb_port": self.smb_port,
            "smb_username": self.smb_username,
            "smb_password": self._encrypt_password(self.smb_password)
            if self.smb_password
            else None,
            "smb_domain": self.smb_domain,
        }


class S3DataConnector(BaseDataConnector):
    """S3-compatible object storage connector (Hetzner, AWS, MinIO, …)."""

    connector_type: Literal["s3"] = "s3"
    endpoint_url: str
    bucket: str
    s3_prefix: str = ""
    access_key: str
    secret_key: str = ""  # Encrypted at rest via Fernet
    region: str = "fsn1"

    # Common fields shared with LocalFsDataConnector
    watch: bool = False
    initial_scan: bool = True
    auto_process_new: bool = True
    poll_interval_seconds: int = Field(default=300, ge=30)

    _TYPE_DEFINITION: ClassVar[DataConnectorTypeDefinition] = (
        DataConnectorTypeDefinition(
            connector_type="s3",
            label="S3-Compatible Storage",
            description="Connect to S3-compatible object storage (Hetzner, AWS, MinIO).",
            fields=[
                DataConnectorFieldDefinition(
                    key="endpoint_url",
                    label="Endpoint URL",
                    description="S3 endpoint URL.",
                    required=True,
                    input_type="text",
                    placeholder="https://fsn1.your-objectstorage.com",
                ),
                DataConnectorFieldDefinition(
                    key="bucket",
                    label="Bucket",
                    description="S3 bucket name.",
                    required=True,
                    input_type="text",
                ),
                DataConnectorFieldDefinition(
                    key="s3_prefix",
                    label="Prefix",
                    description="Optional key prefix (acts as root directory).",
                    input_type="text",
                ),
                DataConnectorFieldDefinition(
                    key="access_key",
                    label="Access Key",
                    description="S3 access key ID.",
                    required=True,
                    input_type="text",
                ),
                DataConnectorFieldDefinition(
                    key="secret_key",
                    label="Secret Key",
                    description="S3 secret access key (stored encrypted).",
                    required=True,
                    input_type="password",
                ),
                DataConnectorFieldDefinition(
                    key="region",
                    label="Region",
                    description="S3 region (default: fsn1 for Hetzner).",
                    input_type="text",
                    placeholder="fsn1",
                ),
            ],
        )
    )

    @field_validator("endpoint_url")
    @classmethod
    def _validate_endpoint_url(cls, value: str) -> str:
        candidate = value.strip().rstrip("/")
        if not candidate:
            raise ValueError("endpoint_url is required")
        if not candidate.startswith(("http://", "https://")):
            raise ValueError("endpoint_url must start with http:// or https://")
        return candidate

    @field_validator("bucket")
    @classmethod
    def _validate_bucket(cls, value: str) -> str:
        candidate = value.strip()
        if not candidate:
            raise ValueError("bucket is required")
        return candidate

    @field_validator("s3_prefix")
    @classmethod
    def _validate_s3_prefix(cls, value: str) -> str:
        return value.strip().strip("/")

    @property
    def is_filesystem_source(self) -> bool:
        return False

    @classmethod
    def type_definition(cls) -> DataConnectorTypeDefinition:
        return cls._TYPE_DEFINITION

    def get_adapter(self) -> "DataConnectorAdapter":
        from services.adapters.s3 import S3Adapter

        return S3Adapter(self)

    @staticmethod
    def _encrypt_secret(secret: str) -> str:
        from services.crypto import encrypt_value

        return encrypt_value(secret)

    def to_db_payload(self) -> dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "source_type": self.connector_type,
            "path": f"s3://{self.bucket}/{self.s3_prefix}".rstrip("/"),
            "endpoint_url": self.endpoint_url,
            "bucket": self.bucket,
            "s3_prefix": self.s3_prefix,
            "access_key": self.access_key,
            "secret_key": self._encrypt_secret(self.secret_key)
            if self.secret_key
            else None,
            "region": self.region,
            "immutable": self.immutable,
            "watch": self.watch,
            "initial_scan": self.initial_scan,
            "auto_process_new": self.auto_process_new,
            "poll_interval_seconds": self.poll_interval_seconds,
            # LocalFS-only fields — keep DB defaults
            "force_polling": False,
            "watcher_type": "auto",
        }


_CONNECTOR_REGISTRY: Dict[str, type[BaseDataConnector]] = {
    "local_fs": LocalFsDataConnector,
    "s3": S3DataConnector,
}


def normalize_connector_type(connector_type: str | None) -> str:
    """Normalize connector type values to canonical lowercase identifiers."""
    normalized = (connector_type or "local_fs").strip().lower()
    return normalized or "local_fs"


def connector_from_payload(payload: dict[str, Any]) -> BaseDataConnector:
    """Instantiate a typed connector model from a payload dict."""
    data = dict(payload)

    connector_type = normalize_connector_type(
        str(data.get("connector_type") or data.get("source_type") or "local_fs")
    )
    model_cls = _CONNECTOR_REGISTRY.get(connector_type)
    if model_cls is None:
        raise ValueError(f"unsupported connector_type: {connector_type}")

    data["connector_type"] = connector_type
    data.pop("source_type", None)
    return model_cls(**data)


def list_connector_type_definitions() -> list[DataConnectorTypeDefinition]:
    """Return type metadata for all registered connector kinds."""
    return [model.type_definition() for model in _CONNECTOR_REGISTRY.values()]
