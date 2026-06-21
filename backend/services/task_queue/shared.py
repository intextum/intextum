"""Shared task queue constants and content-kind helpers."""

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mp3", ".wav", ".m4a"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".xlsx",
    ".pptx",
    ".html",
    ".md",
    ".txt",
    ".eml",
}

VALID_WORKER_CAPABILITIES = frozenset({"document", "image", "video", "training"})
VALID_CONTENT_KINDS = VALID_WORKER_CAPABILITIES
TRAINING_TASK_WORKER_CAPABILITY = "training"
TRAINING_TASK_CONTENT_KIND = TRAINING_TASK_WORKER_CAPABILITY
CONTENT_ENRICHMENT_TRAINING_TASK_TYPE = "train_content_enrichment_model"

STALE_CLAIM_MINUTES = 30
STALE_CLAIM_TASK_ERROR = "Stale claim - worker did not complete in time"
STALE_CLAIM_RETRY_ERROR = "Stale claim - re-queued"
STALE_CLAIM_FAILED_ERROR = "Stale claim - max retries exceeded"


def classify_worker_capability(relative_path: str) -> str | None:
    """Map file extension to the worker capability stored in task_queue.content_kind."""
    suffix = (
        "." + relative_path.rsplit(".", 1)[-1].lower() if "." in relative_path else ""
    )
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in DOCUMENT_EXTENSIONS:
        return "document"
    return None


def is_content_enrichment_training_task_type(task_type: str | None) -> bool:
    """Return whether one task type string represents content enrichment training."""
    return task_type == CONTENT_ENRICHMENT_TRAINING_TASK_TYPE
