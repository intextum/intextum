"""Upload batching helpers for the worker backend client."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import requests

from intextum_worker.models import (
    WorkerUploadBatchResponse,
    WorkerUploadDirectoryResult,
)
from intextum_worker.services.api_client_api import (
    build_worker_url,
    typed_json_response,
)

logger = logging.getLogger(__name__)


def upload_extracted_batch(
    session: requests.Session,
    base_url: str,
    content_item_id: str,
    batch: list[Path],
    *,
    base_dir: Path,
    task_id: str,
    task_secret: str,
    timeout: tuple[int, int],
) -> WorkerUploadBatchResponse:
    """Upload one batch of extracted files and parse the typed batch response."""
    sub_paths = [str(file_path.relative_to(base_dir)) for file_path in batch]
    url = build_worker_url(
        base_url, f"/api/worker/upload-extracted-batch/{content_item_id}"
    )

    file_handles = []
    try:
        files_payload = []
        for file_path in batch:
            handle = open(file_path, "rb")  # noqa: SIM115
            file_handles.append(handle)
            files_payload.append(("files", (file_path.name, handle)))

        resp = session.post(
            url,
            data={"sub_paths": json.dumps(sub_paths)},
            files=files_payload,
            timeout=timeout,
            headers={"X-Task-Id": task_id, "X-Task-Secret": task_secret},
        )
        return typed_json_response(resp, WorkerUploadBatchResponse)
    finally:
        for handle in file_handles:
            handle.close()


def upload_extracted_directory(
    session: requests.Session,
    base_url: str,
    content_item_id: str,
    local_dir: Path,
    task_id: str,
    task_secret: str,
    *,
    timeout: tuple[int, int],
    batch_size: int = 10,
) -> WorkerUploadDirectoryResult:
    """Upload all files in a directory to the backend using batching."""
    base = local_dir.resolve()
    all_files = [
        file_path for file_path in sorted(base.rglob("*")) if file_path.is_file()
    ]
    uploaded = 0
    uploaded_files = []
    batch_results = []

    for index in range(0, len(all_files), batch_size):
        batch = all_files[index : index + batch_size]
        result = upload_extracted_batch(
            session,
            base_url,
            content_item_id,
            batch,
            base_dir=base,
            task_id=task_id,
            task_secret=task_secret,
            timeout=timeout,
        )
        batch_results.append(result)
        uploaded += result.uploaded
        uploaded_files.extend(result.files)
        logger.info(
            "Batch uploaded %d files for content_item_id=%s",
            result.uploaded,
            content_item_id,
        )

    logger.info(
        "Total uploaded %d files for content_item_id=%s", uploaded, content_item_id
    )
    return WorkerUploadDirectoryResult(
        content_item_id=content_item_id,
        uploaded=uploaded,
        files=uploaded_files,
        batches=batch_results,
    )
