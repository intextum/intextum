"""File statistics endpoints."""

import logging
from typing import List

from fastapi import APIRouter, Depends, Query

from auth.dependencies import require_user
from models.content.items import ContentItemInfo
from models.user import User
from services.content import ContentStatsService
from .helpers import get_content_stats_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/stats")
async def get_global_stats(
    user: User = Depends(require_user),
    stats_service: ContentStatsService = Depends(get_content_stats_service),
):
    """
    Get global statistics for intextum.
    """
    return await stats_service.get_global_stats(user)


@router.get("/recent", response_model=List[ContentItemInfo])
async def get_recent_files(
    limit: int = Query(
        default=10, ge=1, le=50, description="Number of recent files to return"
    ),
    user: User = Depends(require_user),
    stats_service: ContentStatsService = Depends(get_content_stats_service),
):
    """
    Get recently processed files that the user has access to.
    """
    return await stats_service.get_recently_indexed(user, limit)
