"""Admin endpoints for group management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_admin
from database import get_db
from models.user import User
from services.group import DuplicateGroupAliasError, GroupService

from .common import (
    CreateGroupRequest,
    GroupEntry,
    UpdateGroupRequest,
    group_entry,
)

router = APIRouter()


@router.get("/groups")
async def list_groups(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[GroupEntry]:
    """List app-managed groups (admin only)."""
    _ = user
    groups = await GroupService(db).list_groups()
    return [group_entry(group) for group in groups]


@router.post("/groups", status_code=status.HTTP_201_CREATED)
async def create_group(
    body: CreateGroupRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> GroupEntry:
    """Create an app-managed group (admin only)."""
    _ = user
    try:
        group = await GroupService(db).create_group(
            slug=body.slug,
            display_name=body.display_name,
            description=body.description,
            proxy_aliases=body.proxy_aliases,
        )
    except DuplicateGroupAliasError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return group_entry(group)


@router.patch("/groups/{slug}")
async def update_group(
    slug: str,
    body: UpdateGroupRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> GroupEntry:
    """Update group metadata and proxy aliases (admin only)."""
    _ = user
    try:
        group = await GroupService(db).update_group(
            slug=slug,
            display_name=body.display_name,
            description=body.description,
            proxy_aliases=body.proxy_aliases,
        )
    except DuplicateGroupAliasError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    return group_entry(group)


@router.delete("/groups/{slug}")
async def delete_group(
    slug: str,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete an app-managed group (admin only)."""
    _ = user
    removed = await GroupService(db).delete_group(slug)
    if not removed:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"removed": True}
