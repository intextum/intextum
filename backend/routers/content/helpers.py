"""Helper functions for files router."""

from pathlib import Path
from typing import Awaitable, Callable, Optional, Set, TypeVar

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings, BaseDataConnector
from database import get_db
from models.sqlalchemy_models import ContentItemEnrichmentState
from models.user import User
from models.task_queue import EnqueueProcessTask, ProcessTaskMetadata
from services.content import ContentService, ContentStatsService
from services.content.access import resolve_source_target
from services.content.metadata import metadata_float, metadata_int
from services.utils import (
    get_content_item_metadata,
    compute_content_item_id,
    find_folder_by_name,
)

T = TypeVar("T")


PREVIEW_MIME_TYPES: Set[str] = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "text/plain",
    "text/markdown",
    "application/json",
    "video/mp4",
    "video/webm",
    "video/ogg",
    "video/quicktime",
    "audio/mpeg",
    "audio/mp4",
    "audio/mp4a-latm",
    "audio/wav",
    "audio/ogg",
    "audio/flac",
    "audio/aac",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

EXTENSION_MIME_MAP: dict[str, str] = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".json": "application/json",
    ".xml": "application/xml",
    ".html": "text/html",
    ".htm": "text/html",
    ".css": "text/css",
    ".js": "text/javascript",
    ".py": "text/plain",
    ".yaml": "text/plain",
    ".yml": "text/plain",
    ".toml": "text/plain",
    ".ini": "text/plain",
    ".cfg": "text/plain",
    ".log": "text/plain",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".m4a": "audio/mp4",
}


def get_content_service(db: AsyncSession = Depends(get_db)) -> ContentService:
    """Dependency to get file service instance."""
    return ContentService(db=db)


def get_content_stats_service(
    db: AsyncSession = Depends(get_db),
) -> ContentStatsService:
    """Dependency to get file stats service instance."""
    return ContentStatsService(db=db)


def _entry_metadata(
    entry, content_item_id: str, *, source_name: str | None = None
) -> ProcessTaskMetadata:
    return ProcessTaskMetadata(
        content_item_id=content_item_id,
        size_bytes=entry.size_bytes,
        modified_time=entry.modified_time,
        created_time=entry.change_time,
        is_symlink=entry.is_symlink,
        file_extension=Path(entry.name).suffix.lower() or None,
        source_name=source_name,
    )


def _metadata_from_path(folder: BaseDataConnector, path_obj: Path) -> tuple[str, dict]:
    metadata = get_content_item_metadata(path_obj)
    try:
        relative_path = str(path_obj.resolve().relative_to(Path(folder.path).resolve()))
    except (ValueError, AttributeError):
        raise ValueError("File not in a data folder")
    return relative_path, metadata


async def run_file_service_operation(
    operation: Callable[[], Awaitable[T]],
    *,
    allow_value_error: bool = False,
) -> T:
    """Execute a file service call and map common domain errors to HTTP errors."""
    try:
        return await operation()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        if allow_value_error:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise


def resolve_extracted_asset_path(
    asset_path: str, extracted_root: Optional[Path] = None
) -> tuple[str, Path]:
    """Resolve extracted asset path and enforce EXTRACTED_DATA_DIR boundary."""
    stripped = asset_path.strip("/")
    if not stripped:
        raise HTTPException(status_code=400, detail="Invalid asset path")

    content_item_id = stripped.split("/", 1)[0]
    if not content_item_id:
        raise HTTPException(status_code=400, detail="Invalid asset path")

    if extracted_root is None:
        settings = get_settings()
        resolved_root = Path(settings.EXTRACTED_DATA_DIR).resolve()
    else:
        resolved_root = extracted_root.resolve()
    full_path = (resolved_root / stripped).resolve()

    try:
        full_path.relative_to(resolved_root)
    except ValueError as exc:
        raise HTTPException(
            status_code=403, detail="Access denied: path traversal detected"
        ) from exc

    return content_item_id, full_path


def resolve_extracted_dir(file_path: str) -> Optional[Path]:
    """Find extracted data dir by content_item_id using folder-name-prefixed path."""
    settings = get_settings()
    extracted_root = Path(settings.EXTRACTED_DATA_DIR)

    stripped = file_path.strip("/")
    if not stripped:
        return None

    parts = stripped.split("/", 1)
    folder = find_folder_by_name(parts[0])
    if not folder:
        # Non-browsable connector content may still need its extracted assets
        # in the details dialog once the content item has been authorized.
        from services.connector import ConnectorRuntimeService

        for connector in ConnectorRuntimeService().all_connectors():
            if connector.name == parts[0]:
                folder = connector
                break
        if not folder:
            return None

    relative_path = parts[1] if len(parts) > 1 else ""
    content_item_id = compute_content_item_id(folder.uuid, relative_path)
    file_id_dir = extracted_root / content_item_id
    if file_id_dir.exists():
        return file_id_dir

    return None


def ensure_existing_file(path: Path, not_found_detail: str = "File not found") -> None:
    """Ensure path exists and points to a file."""
    if not path.exists():
        raise HTTPException(status_code=404, detail=not_found_detail)
    if not path.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")


async def resolve_authorized_source_file(
    file_path: str,
    user: Optional[User],
    file_service: ContentService,
) -> tuple[BaseDataConnector, str]:
    """Resolve and authorize a file path for any source type."""
    resolved = await run_file_service_operation(
        lambda: resolve_source_target(
            file_service.db,
            file_path,
            user,
            expect_dir=False,
        ),
        allow_value_error=True,
    )
    return resolved.folder, resolved.relative_path


async def resolve_authorized_source_dir(
    directory_path: str,
    user: Optional[User],
    file_service: ContentService,
) -> tuple[BaseDataConnector, str]:
    """Resolve and authorize a directory path for any source type."""
    resolved = await run_file_service_operation(
        lambda: resolve_source_target(
            file_service.db,
            directory_path,
            user,
            expect_dir=True,
        ),
        allow_value_error=True,
    )
    return resolved.folder, resolved.relative_path


async def enqueue_single_file(
    folder: BaseDataConnector,
    path_or_rel: Path | str,
    db: AsyncSession,
    processing_config: dict[str, object] | None = None,
    requested_by_sub: str | None = None,
) -> dict:
    """Enqueue a single file for processing."""
    from services.task_queue import TaskQueueService

    if isinstance(path_or_rel, Path):
        try:
            relative_path, path_metadata = _metadata_from_path(folder, path_or_rel)
        except ValueError:
            return {"path": str(path_or_rel), "error": "File not in a data folder"}
    else:
        relative_path = path_or_rel
        adapter = folder.get_adapter()
        entry = await adapter.stat(relative_path)
        content_item_id = compute_content_item_id(folder.uuid, relative_path)
        task_metadata = _entry_metadata(
            entry,
            content_item_id,
            source_name=folder.name,
        )

    content_item_id = compute_content_item_id(folder.uuid, relative_path)
    processing_config = await _processing_config_with_current_class_override(
        db,
        content_item_id,
        processing_config,
    )
    if isinstance(path_or_rel, Path):
        task_metadata = ProcessTaskMetadata(
            content_item_id=content_item_id,
            size_bytes=metadata_int(path_metadata, "size_bytes"),
            modified_time=metadata_float(path_metadata, "modified_time"),
            created_time=metadata_float(path_metadata, "created_time"),
            is_symlink=bool(path_metadata.get("is_symlink", False)),
            file_extension=Path(relative_path).suffix.lower() or None,
            source_name=folder.name,
            processing_config=processing_config,
        )
    elif processing_config is not None:
        task_metadata = task_metadata.model_copy(
            update={"processing_config": processing_config}
        )

    svc = TaskQueueService(db)
    task_id = await svc.enqueue_process(
        EnqueueProcessTask(
            content_item_id=content_item_id,
            folder_uuid=folder.uuid,
            relative_path=relative_path,
            metadata=task_metadata,
            requested_by_sub=requested_by_sub,
        ),
    )
    return {"path": relative_path, "task_id": task_id}


def _should_force_current_class_for_enrichment_rerun(
    processing_config: dict[str, object] | None,
) -> bool:
    if not processing_config:
        return False
    if processing_config.get("enrichment_only") is not True:
        return False
    if processing_config.get("document_enrichment") is not True:
        return False
    return not (
        processing_config.get("forced_document_class_id")
        or processing_config.get("forced_document_class_label")
    )


async def _processing_config_with_current_class_override(
    db: AsyncSession,
    content_item_id: str,
    processing_config: dict[str, object] | None,
) -> dict[str, object] | None:
    if not _should_force_current_class_for_enrichment_rerun(processing_config):
        return processing_config

    state = await db.scalar(
        select(ContentItemEnrichmentState).where(
            ContentItemEnrichmentState.content_item_id == content_item_id
        )
    )
    if state is None:
        return processing_config
    if processing_config is None:
        return None

    class_id = state.classification_override_class_id
    class_label = state.classification_override_label
    if not (class_id or class_label):
        return processing_config

    updated_config = dict(processing_config)
    if class_id:
        updated_config["forced_document_class_id"] = class_id
    if class_label:
        updated_config["forced_document_class_label"] = class_label
    return updated_config
