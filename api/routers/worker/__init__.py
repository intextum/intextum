"""Worker API router package."""

from fastapi import APIRouter

from . import content, tasks, proxy

router = APIRouter()

router.include_router(content.router)
router.include_router(tasks.router)
router.include_router(proxy.router)
