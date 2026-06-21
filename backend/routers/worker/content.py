"""Worker API file endpoints."""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth.worker_auth import require_worker_token
from config import get_settings
from database import get_db
from services.adapters.base import ContentEntry, DataConnectorAdapter
from services.processing_artifacts import ProcessingArtifactService
from services.utils import get_content_item_metadata
from .helpers import (
    authorize_extracted_upload,
    parse_batch_sub_paths,
    reject_oversized_content_length,
    resolve_authorized_worker_file,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def _resolve_local_source_file(
    adapter: DataConnectorAdapter, relative_path: str
) -> Path | None:
    local_path = await adapter.get_local_path(relative_path)
    if local_path:
        if not local_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
    return local_path


def _source_file_metadata(entry: ContentEntry) -> dict[str, object]:
    return {
        "size_bytes": entry.size_bytes,
        "modified_time": entry.modified_time,
        "created_time": entry.change_time,
        "is_symlink": entry.is_symlink,
        "file_extension": Path(entry.name).suffix.lower() or None,
    }


def _ok_response(**values: object) -> dict[str, object]:
    return {"status": "ok", **values}


def _cleanup_written_targets(targets: list[Path]) -> None:
    for target in targets:
        target.unlink(missing_ok=True)


async def _download_source_file(adapter: DataConnectorAdapter, relative_path: str):
    local_path = await _resolve_local_source_file(adapter, relative_path)
    if local_path:
        return FileResponse(
            path=local_path,
            filename=local_path.name,
            media_type="application/octet-stream",
        )

    if not await adapter.is_file(relative_path):
        raise HTTPException(status_code=404, detail="File not found")

    stream = await adapter.read_file(relative_path)
    return StreamingResponse(
        stream,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{Path(relative_path).name}"'
        },
    )


async def _collect_source_file_metadata(
    adapter: DataConnectorAdapter, relative_path: str
) -> dict[str, object]:
    local_path = await _resolve_local_source_file(adapter, relative_path)
    if local_path:
        return get_content_item_metadata(local_path)

    try:
        entry = await adapter.stat(relative_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc

    return _source_file_metadata(entry)


@router.get("/download/{folder_uuid}/{file_path:path}")
async def download_file(
    folder_uuid: str,
    file_path: str,
    request: Request,
    worker_id: str = Depends(require_worker_token),
    db: AsyncSession = Depends(get_db),
):
    """Download a source file from a data folder."""
    folder, file_ref = await resolve_authorized_worker_file(
        folder_uuid,
        file_path,
        request,
        db,
        worker_id,
    )
    return await _download_source_file(folder.get_adapter(), file_ref.relative_path)


@router.get("/file-metadata/{folder_uuid}/{file_path:path}")
async def get_content_item_metadata_endpoint(
    folder_uuid: str,
    file_path: str,
    request: Request,
    worker_id: str = Depends(require_worker_token),
    db: AsyncSession = Depends(get_db),
):
    """Get file metadata including deterministic content_item_id."""
    folder, file_ref = await resolve_authorized_worker_file(
        folder_uuid,
        file_path,
        request,
        db,
        worker_id,
    )
    adapter = folder.get_adapter()
    metadata = await _collect_source_file_metadata(adapter, file_ref.relative_path)
    metadata["content_item_id"] = file_ref.content_item_id
    return metadata


@router.post("/upload-extracted/{content_item_id}")
async def upload_extracted_file(
    content_item_id: str,
    request: Request,
    sub_path: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    worker_id: str = Depends(require_worker_token),
):
    """Upload a single extracted file."""
    task = await authorize_extracted_upload(
        request,
        content_item_id=content_item_id,
        db=db,
        worker_id=worker_id,
    )
    settings = get_settings()
    max_file_size = settings.MAX_UPLOAD_FILE_SIZE_BYTES
    cleaned_sub_path = sub_path.strip("/")

    reject_oversized_content_length(request, max_bytes=max_file_size, size_label="file")

    _, size = await ProcessingArtifactService(settings.EXTRACTED_DATA_DIR).write_upload(
        task_id=task.task_id,
        sub_path=cleaned_sub_path,
        upload=file,
        max_file_size=max_file_size,
    )
    return _ok_response(path=f"{content_item_id}/{cleaned_sub_path}", size=size)


@router.post("/upload-extracted-batch/{content_item_id}")
async def upload_extracted_batch(
    content_item_id: str,
    request: Request,
    sub_paths: str = Form(...),
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    worker_id: str = Depends(require_worker_token),
):
    """Upload multiple extracted files with sub-path support."""
    task = await authorize_extracted_upload(
        request,
        content_item_id=content_item_id,
        db=db,
        worker_id=worker_id,
    )
    settings = get_settings()
    max_file_size = settings.MAX_UPLOAD_FILE_SIZE_BYTES
    max_batch_size = settings.MAX_UPLOAD_BATCH_SIZE_BYTES

    reject_oversized_content_length(
        request, max_bytes=max_batch_size, size_label="batch"
    )

    paths = parse_batch_sub_paths(sub_paths, expected_count=len(files))

    artifact_service = ProcessingArtifactService(settings.EXTRACTED_DATA_DIR)

    results = []
    total_size = 0
    written_targets: list[Path] = []
    try:
        for upload, sub_path in zip(files, paths):
            target, file_size = await artifact_service.write_upload(
                task_id=task.task_id,
                sub_path=sub_path,
                upload=upload,
                max_file_size=max_file_size,
            )
            written_targets.append(target)

            total_size += file_size
            if total_size > max_batch_size:
                raise HTTPException(
                    status_code=413,
                    detail=f"Batch exceeds max total upload size of {max_batch_size} bytes",
                )
            results.append({"path": sub_path, "size": file_size})
    except Exception:
        _cleanup_written_targets(written_targets)
        raise

    return _ok_response(
        content_item_id=content_item_id,
        uploaded=len(results),
        files=results,
    )
