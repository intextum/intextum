"""Files router package."""

from fastapi import APIRouter

from . import audit, browsing, chat, enrichment, extracted, mutations, processing, stats

router = APIRouter()

router.include_router(audit.router)
router.include_router(browsing.router)
router.include_router(chat.router)
router.include_router(enrichment.router)
router.include_router(processing.router)
router.include_router(extracted.router)
router.include_router(mutations.router)
router.include_router(stats.router)
