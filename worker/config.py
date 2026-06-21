"""Configuration settings for the worker service."""

import json
from collections.abc import Iterable
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

VALID_WORKER_CAPABILITIES = frozenset({"document", "image", "video", "training"})
DEFAULT_WORKER_CAPABILITIES = "document,video,image"


def parse_capabilities(value: object) -> list[str]:
    """Parse and validate worker capabilities from env or CLI input."""
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("["):
            try:
                decoded = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "CAPABILITIES must be a comma-separated string or JSON array"
                ) from exc
            return parse_capabilities(decoded)
        values: Iterable[object] = raw.split(",")
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        raise ValueError("CAPABILITIES must be a comma-separated string or JSON array")

    capabilities = [str(item).strip().lower() for item in values if str(item).strip()]
    invalid = sorted(set(capabilities) - VALID_WORKER_CAPABILITIES)
    if invalid:
        allowed = ", ".join(sorted(VALID_WORKER_CAPABILITIES))
        rejected = ", ".join(invalid)
        raise ValueError(
            f"Invalid CAPABILITIES value(s): {rejected}. Allowed: {allowed}"
        )
    return capabilities


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Remote backend connection
    BACKEND_URL: str = "http://backend:8000"
    WORKER_TOKEN: str = ""
    WORK_DIR: str = "/tmp/worker"

    # Poll loop. "training" stays opt-in and must be added explicitly.
    CAPABILITIES: str = DEFAULT_WORKER_CAPABILITIES

    @property
    def parsed_capabilities(self) -> list[str]:
        """Return validated capabilities without triggering pydantic JSON env parsing."""
        return parse_capabilities(self.CAPABILITIES)

    POLL_INTERVAL: float = 5.0
    TASK_HEARTBEAT_INTERVAL_SECONDS: float = 60.0
    CONTENT_ENRICHMENT_STAGE_TIMEOUT_SECONDS: float = 300.0

    # Local processing settings
    CLASSIFICATION_DEVICE: str = "cpu"
    DOCLING_THREADS: int = 4
    DOCLING_OCR_ENGINE: str = "easyocr"
    ASR_MODEL: str = "whisper_large_v3"
    ASR_LANGUAGE: str = "de"
    KEEP_MODELS_LOADED: bool = False

    CUSTOM_FIELD_ID: int = 1

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("DOCLING_OCR_ENGINE", mode="before")
    @classmethod
    def normalize_docling_ocr_engine(cls, value: str) -> str:
        """Normalize and validate configured Docling OCR engine."""
        engine = str(value).strip().lower()
        allowed = {"easyocr", "rapidocr", "tesseract", "tesseract_cli", "ocrmac"}
        if engine not in allowed:
            allowed_list = ", ".join(sorted(allowed))
            raise ValueError(f"DOCLING_OCR_ENGINE must be one of: {allowed_list}")
        return engine


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
