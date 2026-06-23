"""Admin endpoints for data connector management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_admin
from database import get_db
from models.user import User
from services.connector import DataConnectorService

from .common import (
    CreateDataConnectorRequest,
    DataConnectorEntry,
    DataConnectorTypeEntry,
    UpdateDataConnectorRequest,
    load_scan_status_map,
    reload_watcher_configuration,
    stop_watcher_for_connector,
    to_data_connector_entry,
)

router = APIRouter()


@router.get("/data-connectors")
async def list_data_connectors(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[DataConnectorEntry]:
    """List configured data connectors (admin only)."""
    _ = user
    connector_svc = DataConnectorService(db)
    connectors = await connector_svc.list_connectors()
    status_map = await load_scan_status_map(db, [c.uuid for c in connectors])
    return [
        to_data_connector_entry(connector, status_map.get(connector.uuid))
        for connector in connectors
    ]


@router.get("/data-connector-types")
async def list_data_connector_types(
    user: User = Depends(require_admin),
) -> list[DataConnectorTypeEntry]:
    """List supported connector types and their field definitions (admin only)."""
    _ = user
    return [
        DataConnectorTypeEntry.model_validate(type_def.model_dump())
        for type_def in DataConnectorService.list_connector_types()
    ]


@router.post("/data-connectors", status_code=201)
async def create_data_connector(
    request: Request,
    body: CreateDataConnectorRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> DataConnectorEntry:
    """Create a new data connector (admin only)."""
    _ = user
    connector_svc = DataConnectorService(db)
    try:
        fields = body.model_dump(exclude_none=True, exclude={"uuid"})
        connector = await connector_svc.create_connector(uuid=body.uuid, **fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await reload_watcher_configuration(request)
    return to_data_connector_entry(connector)


@router.patch("/data-connectors/{connector_uuid}")
async def update_data_connector(
    request: Request,
    connector_uuid: str,
    body: UpdateDataConnectorRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> DataConnectorEntry:
    """Update a data connector (admin only)."""
    _ = user
    connector_svc = DataConnectorService(db)
    try:
        fields = body.model_dump(exclude_none=True)
        connector = await connector_svc.update_connector(connector_uuid, **fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if connector is None:
        raise HTTPException(status_code=404, detail="Unknown data connector")
    await reload_watcher_configuration(request)
    status_map = await load_scan_status_map(db, [connector.uuid])
    return to_data_connector_entry(connector, status_map.get(connector.uuid))


@router.delete("/data-connectors/{connector_uuid}")
async def delete_data_connector(
    request: Request,
    connector_uuid: str,
    force: bool = False,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a data connector (admin only)."""
    _ = user
    if force:
        await stop_watcher_for_connector(request, connector_uuid)

    connector_svc = DataConnectorService(db)
    try:
        removed = await connector_svc.delete_connector(connector_uuid, force=force)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail="Unknown data connector")
    await reload_watcher_configuration(request)
    return {"removed": True}
