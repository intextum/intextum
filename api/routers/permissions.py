"""Admin API router aggregation."""

from fastapi import APIRouter

from .admin.common import _normalize_trustee
from .admin.ai_settings import router as ai_settings_router
from .admin.chat_prompt_presets import router as chat_prompt_presets_router
from .admin.content_imports import router as content_imports_router
from .admin.content_enrichment_catalog import (
    router as content_enrichment_catalog_router,
)
from .admin.content_enrichment_training import (
    router as content_enrichment_training_router,
)
from .admin.data_connectors import router as data_connectors_router
from .admin.groups import router as groups_router
from .admin.connector_permissions import router as connector_permissions_router
from .admin.users import router as users_router

router = APIRouter()
router.include_router(ai_settings_router)
router.include_router(chat_prompt_presets_router)
router.include_router(content_imports_router)
router.include_router(content_enrichment_catalog_router)
router.include_router(content_enrichment_training_router)
router.include_router(connector_permissions_router)
router.include_router(data_connectors_router)
router.include_router(groups_router)
router.include_router(users_router)

__all__ = ["router", "_normalize_trustee"]
