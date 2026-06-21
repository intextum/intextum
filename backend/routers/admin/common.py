"""Shared admin router models and helpers."""

from __future__ import annotations

import inspect
import logging
from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from config import get_settings
from models.sqlalchemy_models import DataSource
from services.connector import DataConnectorService
from services.group import normalize_group_slug

logger = logging.getLogger(__name__)


class PermissionEntry(BaseModel):
    connector_uuid: str
    trustee: str
    access: str = "allow"
    granted_by: Optional[str] = None
    created_at: Optional[str] = None


class SetPermissionRequest(BaseModel):
    trustee: str
    access: str = "allow"


class UserEntry(BaseModel):
    sub: str
    username: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    auth_display_source: Optional[str] = None
    is_admin: bool = False
    is_disabled: bool = False
    groups: list[str] = Field(default_factory=list)
    providers: list[str] = Field(default_factory=list)
    has_local_credential: bool = False
    first_seen_at: Optional[str] = None
    last_seen_at: Optional[str] = None


class CreateUserRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    is_admin: bool = False
    is_disabled: bool = False
    groups: list[str] = Field(default_factory=list)


class UpdateUserRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    display_name: Optional[str] = None
    is_admin: Optional[bool] = None
    is_disabled: Optional[bool] = None
    groups: Optional[list[str]] = None


class SetUserPasswordRequest(BaseModel):
    password: str
    must_change_password: bool = False


class GroupEntry(BaseModel):
    slug: str
    display_name: str
    description: Optional[str] = None
    proxy_aliases: list[str] = Field(default_factory=list)
    member_count: int = 0


class CreateGroupRequest(BaseModel):
    slug: str
    display_name: str
    description: Optional[str] = None
    proxy_aliases: list[str] = Field(default_factory=list)


class UpdateGroupRequest(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    proxy_aliases: Optional[list[str]] = None


class DataConnectorEntry(BaseModel):
    uuid: str
    name: str
    connector_type: str
    path: str | None = None
    watch: bool
    auto_process_new: bool
    initial_scan: bool
    immutable: bool = False
    force_polling: bool
    poll_interval_seconds: int
    watcher_type: str = "auto"
    smb_server: str | None = None
    smb_share: str | None = None
    smb_port: int = 445
    smb_username: str | None = None
    smb_domain: str | None = None
    endpoint_url: str | None = None
    bucket: str | None = None
    s3_prefix: str | None = None
    access_key: str | None = None
    region: str | None = None


class CreateDataConnectorRequest(BaseModel):
    name: str
    connector_type: str = "local_fs"
    path: Optional[str] = None
    watch: bool = False
    initial_scan: bool = True
    auto_process_new: bool = True
    immutable: bool = False
    force_polling: bool = False
    poll_interval_seconds: int = Field(
        default_factory=lambda: get_settings().CHECK_INTERVAL,
        ge=1,
    )
    uuid: Optional[str] = None
    watcher_type: str = "auto"
    smb_server: Optional[str] = None
    smb_share: Optional[str] = None
    smb_port: int = 445
    smb_username: Optional[str] = None
    smb_password: Optional[str] = None
    smb_domain: Optional[str] = None
    endpoint_url: Optional[str] = None
    bucket: Optional[str] = None
    s3_prefix: Optional[str] = None
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    region: Optional[str] = None

    model_config = {"extra": "forbid"}


class UpdateDataConnectorRequest(BaseModel):
    name: Optional[str] = None
    connector_type: Optional[str] = None
    path: Optional[str] = None
    watch: Optional[bool] = None
    initial_scan: Optional[bool] = None
    auto_process_new: Optional[bool] = None
    immutable: Optional[bool] = None
    force_polling: Optional[bool] = None
    poll_interval_seconds: Optional[int] = Field(default=None, ge=1)
    watcher_type: Optional[str] = None
    smb_server: Optional[str] = None
    smb_share: Optional[str] = None
    smb_port: Optional[int] = None
    smb_username: Optional[str] = None
    smb_password: Optional[str] = None
    smb_domain: Optional[str] = None
    endpoint_url: Optional[str] = None
    bucket: Optional[str] = None
    s3_prefix: Optional[str] = None
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    region: Optional[str] = None

    model_config = {"extra": "forbid"}


class DataConnectorTypeFieldEntry(BaseModel):
    key: str
    label: str
    description: str = ""
    required: bool = False
    input_type: str = "text"
    placeholder: Optional[str] = None


class DataConnectorTypeEntry(BaseModel):
    connector_type: str
    label: str
    description: str
    fields: list[DataConnectorTypeFieldEntry]


def to_data_connector_entry(connector: DataSource) -> DataConnectorEntry:
    return DataConnectorEntry(
        uuid=connector.uuid,
        name=connector.name,
        connector_type=connector.source_type,
        path=connector.path,
        watch=connector.watch,
        auto_process_new=connector.auto_process_new,
        initial_scan=connector.initial_scan,
        immutable=getattr(connector, "immutable", False),
        force_polling=connector.force_polling if connector.watch else False,
        poll_interval_seconds=connector.poll_interval_seconds,
        watcher_type=getattr(connector, "watcher_type", "auto"),
        smb_server=getattr(connector, "smb_server", None),
        smb_share=getattr(connector, "smb_share", None),
        smb_port=getattr(connector, "smb_port", 445),
        smb_username=getattr(connector, "smb_username", None),
        smb_domain=getattr(connector, "smb_domain", None),
        endpoint_url=getattr(connector, "endpoint_url", None),
        bucket=getattr(connector, "bucket", None),
        s3_prefix=getattr(connector, "s3_prefix", None),
        access_key=getattr(connector, "access_key", None),
        region=getattr(connector, "region", None),
    )


def permission_entry(perm) -> PermissionEntry:
    return PermissionEntry(
        connector_uuid=perm.folder_uuid,
        trustee=perm.trustee,
        access=perm.access,
        granted_by=perm.granted_by,
        created_at=perm.created_at.isoformat() if perm.created_at else None,
    )


def user_entry(user) -> UserEntry:
    return UserEntry(
        sub=user.sub,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        auth_display_source=getattr(user, "auth_display_source", None),
        is_admin=user.is_admin,
        is_disabled=getattr(user, "is_disabled", False),
        groups=sorted(
            {
                membership.group_slug
                for membership in getattr(user, "group_memberships", [])
            }
        ),
        providers=sorted(
            {identity.provider for identity in getattr(user, "identities", [])}
        ),
        has_local_credential=getattr(user, "local_credentials", None) is not None,
        first_seen_at=user.first_seen_at.isoformat() if user.first_seen_at else None,
        last_seen_at=user.last_seen_at.isoformat() if user.last_seen_at else None,
    )


def group_entry(group) -> GroupEntry:
    return GroupEntry(
        slug=group.slug,
        display_name=group.display_name,
        description=group.description,
        proxy_aliases=sorted(
            alias.external_value
            for alias in getattr(group, "external_aliases", [])
            if alias.provider == "proxy"
        ),
        member_count=len(getattr(group, "memberships", [])),
    )


async def ensure_connector_exists(
    connector_svc: DataConnectorService, connector_uuid: str
) -> None:
    if await connector_svc.get_connector(connector_uuid) is None:
        raise HTTPException(status_code=404, detail="Unknown data connector")


def watcher_from_request(request: Request):
    return getattr(request.app.state, "watcher", None)


def _normalize_trustee(trustee: str) -> str:
    """Normalize trustee syntax."""
    normalized = trustee.strip()
    if normalized.lower() == "everyone":
        return "everyone"
    if normalized.startswith("sub:") and len(normalized) > len("sub:"):
        return normalized
    if normalized.startswith("group:") and len(normalized) > len("group:"):
        return f"group:{normalize_group_slug(normalized[len('group:') :])}"
    raise HTTPException(
        status_code=400,
        detail="trustee must be 'everyone', 'sub:<id>', or 'group:<slug>'",
    )


async def reload_watcher_configuration(request: Request) -> None:
    """Reload watcher settings after data connector mutations."""
    watcher = watcher_from_request(request)
    if watcher is None:
        logger.warning("Watcher not available on app state; skipping connector reload")
        return

    result = watcher.reload_config()
    if inspect.isawaitable(result):
        await result


async def stop_watcher_for_connector(request: Request, connector_uuid: str) -> None:
    """Stop a single connector watcher before destructive connector deletion."""
    watcher = watcher_from_request(request)
    if watcher is None:
        return

    stop_connector = getattr(watcher, "stop_connector", None)
    if stop_connector is None:
        return

    result = stop_connector(connector_uuid)
    if inspect.isawaitable(result):
        await result
