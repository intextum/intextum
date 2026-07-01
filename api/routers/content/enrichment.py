"""File enrichment verification endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_user
from database import get_db
from models.content.items import (
    ContentItemInfo,
    ContentReviewSubmitRequest,
    ContentVerifyClassRequest,
    ContentVerifyClassResponse,
)
from models.user import User
from services.ai_settings import AiSettingsService
from services.content import ContentService
from services.content.enrichment import (
    ContentReviewConflictError,
    ContentReviewSubmitError,
    ContentVerifyClassError,
    submit_content_enrichment_review,
    verify_content_classification,
)
from services.content.helpers import get_record, record_to_file_info
from services.utils import compute_content_item_id
from .helpers import (
    enqueue_single_file,
    get_content_service,
    resolve_authorized_source_file,
)

router = APIRouter()


@router.post(
    "/verify-class/{file_path:path}", response_model=ContentVerifyClassResponse
)
async def verify_file_classification(
    file_path: str,
    request: ContentVerifyClassRequest,
    user: User = Depends(require_user),
    file_service: ContentService = Depends(get_content_service),
    db: AsyncSession = Depends(get_db),
):
    """Store an unconfirmed class change and queue extraction for that class."""
    folder, rel_path = await resolve_authorized_source_file(
        file_path, user, file_service
    )

    record = await get_record(db, compute_content_item_id(folder.uuid, rel_path))
    if record is None or record.is_dir:
        raise HTTPException(status_code=404, detail=f"File not indexed: {file_path}")

    effective_settings = await AiSettingsService(db).get_effective_settings()
    try:
        (
            updated_record,
            class_id,
            canonical_label,
            should_queue,
        ) = await verify_content_classification(
            db,
            record,
            user=user,
            settings=effective_settings,
            classification_label=request.classification_label,
        )
    except ContentVerifyClassError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    task_id = None
    if should_queue:
        result = await enqueue_single_file(
            folder,
            rel_path,
            db,
            processing_config={
                "enrichment_only": True,
                "document_enrichment": True,
                "forced_document_class_id": class_id,
                "forced_document_class_label": canonical_label,
            },
            requested_by_sub=user.require_stable_sub(),
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        task_id = result.get("task_id")
        refreshed = await get_record(db, compute_content_item_id(folder.uuid, rel_path))
        if refreshed is not None:
            updated_record = refreshed

    return ContentVerifyClassResponse(
        content_item=record_to_file_info(
            updated_record,
            folder,
            effective_settings=effective_settings,
        ),
        task_id=task_id,
    )


@router.post("/review/{file_path:path}", response_model=ContentItemInfo)
async def submit_file_review(
    file_path: str,
    request: ContentReviewSubmitRequest,
    user: User = Depends(require_user),
    file_service: ContentService = Depends(get_content_service),
    db: AsyncSession = Depends(get_db),
):
    """Submit one unified human review decision for a file."""
    folder, rel_path = await resolve_authorized_source_file(
        file_path, user, file_service
    )

    record = await get_record(db, compute_content_item_id(folder.uuid, rel_path))
    if record is None or record.is_dir:
        raise HTTPException(status_code=404, detail=f"File not indexed: {file_path}")

    requested_fields = set(request.model_fields_set)
    update_classification = "classification_label" in requested_fields
    update_extraction = "extraction_data" in requested_fields
    dismiss_classification = bool(request.classification_dismissed)
    dismiss_extraction = bool(request.extraction_dismissed)
    reset_classification = bool(request.classification_reset)
    reset_extraction = bool(request.extraction_reset)

    if sum((update_classification, dismiss_classification, reset_classification)) > 1:
        raise HTTPException(
            status_code=400,
            detail=(
                "classification_label, classification_dismissed and classification_reset"
                " are mutually exclusive"
            ),
        )
    if sum((update_extraction, dismiss_extraction, reset_extraction)) > 1:
        raise HTTPException(
            status_code=400,
            detail=(
                "extraction_data, extraction_dismissed and extraction_reset"
                " are mutually exclusive"
            ),
        )
    if not any(
        (
            update_classification,
            update_extraction,
            dismiss_classification,
            dismiss_extraction,
            reset_classification,
            reset_extraction,
        )
    ):
        raise HTTPException(status_code=400, detail="No review data provided")

    effective_settings = await AiSettingsService(db).get_effective_settings()
    enrichment = record_to_file_info(
        record,
        folder,
        effective_settings=effective_settings,
    ).document_enrichment
    state = record.enrichment_state

    if (
        update_classification
        and enrichment is not None
        and enrichment.classification_lifecycle is not None
        and enrichment.classification_lifecycle.stale
    ):
        submitted_label = (request.classification_label or "").strip() or None
        raw_system_label = (
            state.classification_system_label if state is not None else None
        )
        system_label = (
            raw_system_label.strip()
            if isinstance(raw_system_label, str) and raw_system_label.strip()
            else None
        )
        if submitted_label is not None and submitted_label == system_label:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Classification result is stale; rerun enrichment before"
                    " accepting the system value"
                ),
            )
    if (
        update_extraction
        and enrichment is not None
        and enrichment.extraction_lifecycle is not None
        and enrichment.extraction_lifecycle.stale
    ):
        system_data = state.extraction_data_json if state is not None else None
        if request.extraction_data == system_data:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Extraction result is stale; rerun enrichment before"
                    " accepting the system value"
                ),
            )

    try:
        updated_record = await submit_content_enrichment_review(
            db,
            record,
            user=user,
            classification_label=request.classification_label,
            classification_dismiss_reason=request.classification_dismiss_reason,
            extraction_data=request.extraction_data,
            extraction_dismiss_reason=request.extraction_dismiss_reason,
            update_classification=update_classification,
            update_extraction=update_extraction,
            dismiss_classification=dismiss_classification,
            dismiss_extraction=dismiss_extraction,
            reset_classification=reset_classification,
            reset_extraction=reset_extraction,
        )
    except ContentReviewConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ContentReviewSubmitError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return record_to_file_info(
        updated_record,
        folder,
        effective_settings=effective_settings,
    )
