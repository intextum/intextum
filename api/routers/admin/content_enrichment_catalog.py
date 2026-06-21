"""Admin endpoints for first-class content enrichment catalog resources."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_admin
from database import get_db
from models.content.enrichment_catalog import (
    ContentEnrichmentCatalogResponse,
    ContentEnrichmentCatalogUpdateRequest,
    ContentEnrichmentFieldExampleCandidatesRequest,
    ContentEnrichmentFieldExampleCandidatesResponse,
)
from models.user import User
from services.content.enrichment import (
    ContentEnrichmentCatalogService,
    ContentEnrichmentFieldExampleService,
    UnknownFieldError,
    UnknownSchemaError,
)

router = APIRouter()


@router.get(
    "/content-enrichment-catalog", response_model=ContentEnrichmentCatalogResponse
)
async def get_content_enrichment_catalog(
    _user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentEnrichmentCatalogResponse:
    """Return stored document classes and extraction schemas."""
    return await ContentEnrichmentCatalogService(db).get_catalog()


@router.put(
    "/content-enrichment-catalog", response_model=ContentEnrichmentCatalogResponse
)
async def replace_content_enrichment_catalog(
    request: ContentEnrichmentCatalogUpdateRequest,
    _user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentEnrichmentCatalogResponse:
    """Replace the full content enrichment catalog."""
    try:
        return await ContentEnrichmentCatalogService(db).replace_catalog(
            document_classes=request.document_classes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/content-enrichment-catalog/reset",
    response_model=ContentEnrichmentCatalogResponse,
)
async def reset_content_enrichment_catalog(
    _user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentEnrichmentCatalogResponse:
    """Reset the catalog to deployment defaults."""
    return await ContentEnrichmentCatalogService(db).reset_catalog()


@router.post(
    "/content-enrichment-catalog/schemas/{schema_name}/fields/{field_name}/example-candidates",
    response_model=ContentEnrichmentFieldExampleCandidatesResponse,
)
async def suggest_field_example_candidates(
    schema_name: str,
    field_name: str,
    request: ContentEnrichmentFieldExampleCandidatesRequest,
    _user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentEnrichmentFieldExampleCandidatesResponse:
    """Surface stored extractions on the selected files as candidate field examples."""
    try:
        return await ContentEnrichmentFieldExampleService(db).suggest_candidates(
            schema_name=schema_name,
            field_name=field_name,
            content_item_ids=request.content_item_ids,
        )
    except UnknownSchemaError as exc:
        raise HTTPException(
            status_code=404, detail="Unknown extraction schema"
        ) from exc
    except UnknownFieldError as exc:
        raise HTTPException(status_code=404, detail="Unknown extraction field") from exc
