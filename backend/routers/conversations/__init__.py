"""Conversations router package."""

from fastapi import APIRouter
from .runs import router as run_router
from .router import router as conversation_router

router = APIRouter()
router.include_router(run_router)
router.include_router(conversation_router)
