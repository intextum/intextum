"""Admin endpoints for content enrichment adapter training and registry state."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_admin
from database import get_db
from models.content.enrichment_training import (
    CreateContentEnrichmentFineTuneJobRequest,
    ContentEnrichmentFineTuneJobEntry,
    ContentEnrichmentModelRegistryEntry,
    ContentEnrichmentModelPromotionResponse,
    ContentEnrichmentTrainingOverviewResponse,
)
from models.user import User
from services.content_enrichment_training import ContentEnrichmentTrainingService

router = APIRouter()


@router.get(
    "/content-enrichment-training",
    response_model=ContentEnrichmentTrainingOverviewResponse,
)
async def get_content_enrichment_training_overview(
    _user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentEnrichmentTrainingOverviewResponse:
    """Return training jobs and registry entries for content enrichment adapters."""
    return await ContentEnrichmentTrainingService(db).get_overview()


@router.post(
    "/content-enrichment-training/jobs",
    response_model=ContentEnrichmentFineTuneJobEntry,
)
async def create_content_enrichment_training_job(
    request: CreateContentEnrichmentFineTuneJobRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentEnrichmentFineTuneJobEntry:
    """Queue a new content enrichment fine-tune job."""
    try:
        return await ContentEnrichmentTrainingService(db).create_job(
            request,
            requested_by=user.username,
            requested_by_sub=user.normalized_sub,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/content-enrichment-training/jobs/{job_id}/retry",
    response_model=ContentEnrichmentFineTuneJobEntry,
)
async def retry_content_enrichment_training_job(
    job_id: str,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentEnrichmentFineTuneJobEntry:
    """Queue one fresh retry of a failed training job."""
    try:
        return await ContentEnrichmentTrainingService(db).retry_job(
            job_id,
            requested_by=user.username,
            requested_by_sub=user.normalized_sub,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/content-enrichment-training/jobs/{job_id}/cancel",
    response_model=ContentEnrichmentFineTuneJobEntry,
)
async def cancel_content_enrichment_training_job(
    job_id: str,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentEnrichmentFineTuneJobEntry:
    """Cancel one queued or running content enrichment training job."""
    try:
        return await ContentEnrichmentTrainingService(db).cancel_job(
            job_id,
            cancelled_by=user.username,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete(
    "/content-enrichment-training/jobs/{job_id}",
    status_code=204,
)
async def delete_content_enrichment_training_job(
    job_id: str,
    _user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove one failed or cancelled training job from the history."""
    try:
        await ContentEnrichmentTrainingService(db).delete_job(job_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/content-enrichment-training/models/{model_id}/promote",
    response_model=ContentEnrichmentModelPromotionResponse,
)
async def promote_content_enrichment_model(
    model_id: str,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentEnrichmentModelPromotionResponse:
    """Promote one ready registry model into the live enrichment settings."""
    try:
        return await ContentEnrichmentTrainingService(db).promote_model(
            model_id,
            updated_by=user.username,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/content-enrichment-training/models/{model_id}/archive",
    response_model=ContentEnrichmentModelRegistryEntry,
)
async def archive_content_enrichment_model(
    model_id: str,
    _user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ContentEnrichmentModelRegistryEntry:
    """Archive one inactive ready or failed content enrichment model."""
    try:
        return await ContentEnrichmentTrainingService(db).archive_model(model_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
