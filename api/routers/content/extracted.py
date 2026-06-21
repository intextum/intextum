"""Extracted assets endpoints."""

from copy import deepcopy
import logging
import mimetypes
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_user
from config import get_settings
from database import get_db
from models.content.items import (
    ExtractedAsset,
    ExtractedAssetsResponse,
)
from models.sqlalchemy_models import IndexedContentItem
from models.user import User
from services.content import ContentService
from services.content.docling import (
    description_text_from_meta_value,
    extract_image_metadata_from_docling,
    prediction_list_from_classification,
    rewrite_uris,
)
from services.content.helpers import user_can_access_record
from services.utils import compute_content_item_id
from .helpers import (
    get_content_service,
    resolve_authorized_source_file,
    resolve_extracted_asset_path,
    ensure_existing_file,
)

logger = logging.getLogger(__name__)

router = APIRouter()
INLINE_EXTRACTED_ASSET_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}


async def _get_indexed_content_item_record(
    db: AsyncSession, content_item_id: str
) -> IndexedContentItem | None:
    result = await db.execute(
        select(IndexedContentItem).where(
            IndexedContentItem.content_item_id == content_item_id
        )
    )
    return result.scalar_one_or_none()


async def _resolve_authorized_file_id(
    file_path: str,
    user: User,
    file_service: ContentService,
) -> str:
    folder, rel_path = await resolve_authorized_source_file(
        file_path, user, file_service
    )
    return compute_content_item_id(folder.uuid, rel_path)


def _resolve_extracted_asset_media_type(path: Path) -> str:
    """Allow only non-active image media types for extracted assets."""
    media_type, _ = mimetypes.guess_type(str(path))
    if media_type not in INLINE_EXTRACTED_ASSET_MIME_TYPES:
        raise HTTPException(
            status_code=415, detail="Preview not supported for this asset"
        )
    return media_type


def _split_extracted_assets(
    extracted_dir: Path,
    metadata_map: dict[str, dict[str, str | None]],
) -> tuple[list[ExtractedAsset], list[ExtractedAsset]]:
    image_suffixes = {".png", ".jpg", ".jpeg", ".webp"}
    figures: list[ExtractedAsset] = []
    tables: list[ExtractedAsset] = []
    dir_name = extracted_dir.name

    for img_file in sorted(extracted_dir.iterdir()):
        if not img_file.is_file() or img_file.suffix.lower() not in image_suffixes:
            continue
        meta = metadata_map.get(img_file.name) or {}
        asset_type = meta.get("type") or "figure"
        if asset_type == "page":
            continue
        asset = ExtractedAsset(
            name=img_file.name,
            path=f"{dir_name}/{img_file.name}",
            type=asset_type,
            size_bytes=img_file.stat().st_size,
            classification=meta.get("classification"),
            description=meta.get("description"),
        )
        if asset_type == "table":
            tables.append(asset)
        else:
            figures.append(asset)

    return figures, tables


def _add_docling_component_annotations(document_data: dict[str, Any]) -> None:
    """Expose meta-only picture enrichment in the annotations shape used by docling-components."""
    pictures = document_data.get("pictures")
    if not isinstance(pictures, list):
        return

    for picture in pictures:
        if not isinstance(picture, dict):
            continue
        if isinstance(picture.get("annotations"), list) and picture["annotations"]:
            continue

        meta = picture.get("meta")
        if not isinstance(meta, dict):
            continue

        annotations: list[dict[str, Any]] = []
        predictions = prediction_list_from_classification(meta.get("classification"))
        if predictions:
            annotations.append(
                {"kind": "classification", "predicted_classes": predictions}
            )

        description = description_text_from_meta_value(meta.get("description"))
        if description is not None:
            annotations.append({"kind": "description", "text": description})

        if annotations:
            picture["annotations"] = annotations


def _docling_document_for_viewer(
    document_json: dict[str, Any], *, content_item_id: str
) -> dict[str, Any]:
    document_data = deepcopy(document_json)
    uri_prefix = f"/api/content/extracted-asset/{content_item_id}/"
    rewrite_uris(document_data, uri_prefix, content_item_id)
    _add_docling_component_annotations(document_data)
    return document_data


def _resolve_extracted_dir_for_content_item(content_item_id: str) -> Path | None:
    """Resolve extracted files by authorized content item id."""
    extracted_dir = Path(get_settings().EXTRACTED_DATA_DIR) / content_item_id
    return extracted_dir if extracted_dir.exists() else None


@router.get("/extracted/{file_path:path}", response_model=ExtractedAssetsResponse)
async def get_extracted_assets(
    file_path: str,
    user: User = Depends(require_user),
    file_service: ContentService = Depends(get_content_service),
    db: AsyncSession = Depends(get_db),
):
    """Get extracted figure/table assets for a file."""
    content_item_id = await _resolve_authorized_file_id(file_path, user, file_service)

    extracted_dir = _resolve_extracted_dir_for_content_item(content_item_id)
    if extracted_dir is None:
        record = await _get_indexed_content_item_record(db, content_item_id)
        return ExtractedAssetsResponse(
            file_path=file_path,
            has_extracted_content=False,
            has_docling_document=bool(record and record.document_json),
        )

    record = await _get_indexed_content_item_record(db, content_item_id)
    document_json = record.document_json if record else {}

    metadata_map = extract_image_metadata_from_docling(document_json)
    figures, tables = _split_extracted_assets(extracted_dir, metadata_map)

    return ExtractedAssetsResponse(
        file_path=file_path,
        extracted_dir=extracted_dir.name,
        figures=figures,
        tables=tables,
        has_extracted_content=len(figures) > 0 or len(tables) > 0,
        has_docling_document=bool(document_json),
    )


@router.get("/extracted-document/{file_path:path}")
async def get_extracted_document(
    file_path: str,
    user: User = Depends(require_user),
    file_service: ContentService = Depends(get_content_service),
    db: AsyncSession = Depends(get_db),
):
    """Get extracted `document.json` for a file."""
    content_item_id = await _resolve_authorized_file_id(file_path, user, file_service)
    record = await _get_indexed_content_item_record(db, content_item_id)

    if not record or not record.document_json:
        raise HTTPException(status_code=404, detail="Extracted document not found")

    document_data = _docling_document_for_viewer(
        record.document_json,
        content_item_id=content_item_id,
    )

    return JSONResponse(content=document_data)


@router.get("/extracted-document-by-id/{content_item_id}")
async def get_extracted_document_by_id(
    content_item_id: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Get extracted `document.json` for a file by stable content item id."""
    record = await _get_indexed_content_item_record(db, content_item_id)
    if not record or not record.document_json:
        raise HTTPException(status_code=404, detail="Extracted document not found")
    if not user_can_access_record(record, user):
        raise HTTPException(status_code=403, detail="Access denied")

    document_data = _docling_document_for_viewer(
        record.document_json,
        content_item_id=content_item_id,
    )

    return JSONResponse(content=document_data)


@router.get("/extracted-asset/{asset_path:path}")
async def get_extracted_asset(
    asset_path: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Serve an extracted asset file."""
    extracted_root = Path(get_settings().EXTRACTED_DATA_DIR)
    content_item_id, full_path = resolve_extracted_asset_path(
        asset_path, extracted_root
    )

    rec = await _get_indexed_content_item_record(db, content_item_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    if not user_can_access_record(rec, user):
        raise HTTPException(status_code=403, detail="Access denied")

    ensure_existing_file(full_path, not_found_detail="Asset not found")

    return FileResponse(
        path=full_path,
        media_type=_resolve_extracted_asset_media_type(full_path),
        content_disposition_type="inline",
    )
