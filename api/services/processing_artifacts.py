"""Task-scoped extracted artifact staging and promotion."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile


class ProcessingArtifactService:
    """Manage worker-produced extracted artifacts for processing tasks."""

    def __init__(self, extracted_root: str | Path):
        self.extracted_root = Path(extracted_root).resolve()

    @property
    def staging_root(self) -> Path:
        return self.extracted_root / ".staging"

    def staging_dir(self, task_id: str) -> Path:
        return self._resolve_under(self.staging_root, task_id.strip("/"))

    def canonical_dir(self, content_item_id: str) -> Path:
        return self._resolve_under(self.extracted_root, content_item_id.strip("/"))

    @staticmethod
    def _resolve_under(base_dir: Path, sub_path: str) -> Path:
        base = base_dir.resolve()
        target = (base / sub_path).resolve()
        try:
            target.relative_to(base)
        except ValueError as exc:
            raise HTTPException(
                status_code=403,
                detail="Access denied: path traversal detected",
            ) from exc
        return target

    async def write_upload(
        self,
        *,
        task_id: str,
        sub_path: str,
        upload: UploadFile,
        max_file_size: int,
    ) -> tuple[Path, int]:
        """Write one uploaded extracted file into task staging."""
        cleaned_sub_path = sub_path.strip("/")
        if not cleaned_sub_path:
            raise HTTPException(status_code=400, detail="Invalid upload path")

        task_dir = self.staging_dir(task_id)
        target = self._resolve_under(task_dir, cleaned_sub_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        written = 0
        try:
            with target.open("wb") as handle:
                while chunk := await upload.read(1024 * 1024):
                    written += len(chunk)
                    if written > max_file_size:
                        raise HTTPException(
                            status_code=413,
                            detail=(
                                f"Payload exceeds max file size of {max_file_size} bytes"
                            ),
                        )
                    handle.write(chunk)
        except Exception:
            self._cleanup_partial_upload(target)
            raise
        finally:
            await upload.close()

        return target, written

    @staticmethod
    def _cleanup_partial_upload(target: Path) -> None:
        target.unlink(missing_ok=True)

    def staged_document_json(self, task_id: str) -> dict[str, Any] | None:
        """Parse staged document.json when present."""
        json_file = self.staging_dir(task_id) / "document.json"
        if not json_file.exists():
            return None
        try:
            parsed_json = json.loads(json_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HTTPException(
                status_code=400,
                detail="Invalid JSON in document.json",
            ) from exc
        if not isinstance(parsed_json, dict):
            raise HTTPException(
                status_code=400,
                detail="document.json must contain a JSON object",
            )
        return parsed_json

    @staticmethod
    def _rollback_failed_promotion(
        *,
        promote_dir: Path,
        backup_dir: Path,
        canonical_dir: Path,
    ) -> None:
        if promote_dir.exists():
            shutil.rmtree(promote_dir, ignore_errors=True)
        if backup_dir.exists() and not canonical_dir.exists():
            shutil.move(str(backup_dir), str(canonical_dir))

    @staticmethod
    def _cleanup_promotion_dirs(*dirs: Path) -> None:
        for path in dirs:
            shutil.rmtree(path, ignore_errors=True)

    def promote_staged_output(
        self,
        *,
        task_id: str,
        content_item_id: str,
    ) -> dict[str, Any] | None:
        """Promote staged artifacts to the canonical content-item directory."""
        task_dir = self.staging_dir(task_id)
        if not task_dir.exists():
            return None

        document_json = self.staged_document_json(task_id)
        canonical_dir = self.canonical_dir(content_item_id)
        promote_dir = self._resolve_under(
            self.extracted_root,
            f".promote-{content_item_id}-{task_id}",
        )
        backup_dir = self._resolve_under(
            self.extracted_root,
            f".previous-{content_item_id}-{task_id}",
        )

        shutil.rmtree(promote_dir, ignore_errors=True)
        shutil.rmtree(backup_dir, ignore_errors=True)
        canonical_dir.parent.mkdir(parents=True, exist_ok=True)

        shutil.move(str(task_dir), str(promote_dir))
        try:
            if canonical_dir.exists():
                shutil.move(str(canonical_dir), str(backup_dir))
            shutil.move(str(promote_dir), str(canonical_dir))
        except Exception:
            self._rollback_failed_promotion(
                promote_dir=promote_dir,
                backup_dir=backup_dir,
                canonical_dir=canonical_dir,
            )
            raise
        finally:
            self._cleanup_promotion_dirs(backup_dir, promote_dir)

        return document_json

    def cleanup_task(self, task_id: str) -> None:
        """Remove all staged artifacts for one processing task."""
        shutil.rmtree(self.staging_dir(task_id), ignore_errors=True)
