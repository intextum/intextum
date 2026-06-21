"""Admin endpoints for connector-level permissions."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_admin
from database import get_db
from models.user import User
from services.permission import PermissionService
from services.connector import DataConnectorService

from .common import (
    PermissionEntry,
    SetPermissionRequest,
    _normalize_trustee,
    ensure_connector_exists,
    permission_entry,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def _list_permissions_impl(
    connector_uuid: str,
    db: AsyncSession,
) -> list[PermissionEntry]:
    connector_svc = DataConnectorService(db)
    await ensure_connector_exists(connector_svc, connector_uuid)

    svc = PermissionService(db)
    perms = await svc.get_permissions(connector_uuid)
    return [permission_entry(perm) for perm in perms]


async def _set_permission_impl(
    connector_uuid: str,
    body: SetPermissionRequest,
    user: User,
    db: AsyncSession,
) -> PermissionEntry:
    connector_svc = DataConnectorService(db)
    await ensure_connector_exists(connector_svc, connector_uuid)
    if body.access not in ("allow", "deny"):
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="access must be 'allow' or 'deny'")

    trustee = _normalize_trustee(body.trustee)

    svc = PermissionService(db)
    perm = await svc.set_permission(
        folder_uuid=connector_uuid,
        trustee=trustee,
        access=body.access,
        granted_by=user.username,
    )

    count = await svc.propagate_folder_permissions(connector_uuid)
    logger.info("Propagated connector permissions to %d records", count)

    return permission_entry(perm)


async def _remove_permission_impl(
    connector_uuid: str,
    trustee: str,
    db: AsyncSession,
) -> dict:
    from fastapi import HTTPException

    connector_svc = DataConnectorService(db)
    await ensure_connector_exists(connector_svc, connector_uuid)
    normalized_trustee = _normalize_trustee(trustee)

    svc = PermissionService(db)
    removed = await svc.remove_permission(connector_uuid, normalized_trustee)
    if not removed:
        raise HTTPException(status_code=404, detail="Permission not found")

    count = await svc.propagate_folder_permissions(connector_uuid)
    logger.info("Propagated connector permissions to %d records after removal", count)
    return {"removed": True}


@router.get("/connectors/{connector_uuid}/permissions")
async def list_connector_permissions(
    connector_uuid: str,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[PermissionEntry]:
    """List permissions for a data connector (admin only)."""
    _ = user
    return await _list_permissions_impl(connector_uuid, db)


@router.put("/connectors/{connector_uuid}/permissions")
async def set_connector_permission(
    connector_uuid: str,
    body: SetPermissionRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> PermissionEntry:
    """Set a permission on a data connector (admin only)."""
    return await _set_permission_impl(connector_uuid, body, user, db)


@router.delete("/connectors/{connector_uuid}/permissions/{trustee}")
async def remove_connector_permission(
    connector_uuid: str,
    trustee: str,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Remove a connector permission entry (admin only)."""
    _ = user
    return await _remove_permission_impl(connector_uuid, trustee, db)
