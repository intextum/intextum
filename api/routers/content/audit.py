"""Content audit trail endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_user
from database import get_db
from models.content.audit import ContentAuditEventListResponse
from models.user import User
from services.content import ContentService
from services.content.audit import ContentAuditService
from services.content.helpers import get_record
from services.utils import compute_content_item_id
from .helpers import get_content_service, resolve_authorized_source_file

router = APIRouter()


@router.get("/audit/{file_path:path}", response_model=ContentAuditEventListResponse)
async def list_content_audit_events(
    file_path: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_user),
    file_service: ContentService = Depends(get_content_service),
    db: AsyncSession = Depends(get_db),
):
    """Return audit events for an accessible content item."""
    folder, rel_path = await resolve_authorized_source_file(
        file_path, user, file_service
    )
    content_item_id = compute_content_item_id(folder.uuid, rel_path)
    record = await get_record(db, content_item_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"File not indexed: {file_path}")
    return await ContentAuditService(db).list_for_content_item(
        content_item_id,
        limit=limit,
        offset=offset,
    )
