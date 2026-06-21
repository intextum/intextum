"""Configuration settings for the backend service."""

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from models.connector_types import (
    BaseDataConnector,
    LocalFsDataConnector,
    S3DataConnector,
)
from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "BaseDataConnector",
    "LocalFsDataConnector",
    "S3DataConnector",
    "Settings",
    "collect_production_config_errors",
    "get_settings",
    "is_production_env",
    "validate_production_settings",
]


logger = logging.getLogger(__name__)


class YamlSettingsSource:
    """Pydantic-settings source that reads from a YAML config file."""

    # Maps lowercase YAML keys to Settings field names
    FIELD_MAP: dict[str, str] = {
        "cors_allow_origins": "CORS_ALLOW_ORIGINS_STR",
        "app_env": "APP_ENV",
        "data_volume": "DATA_VOLUME",
        "extracted_data_dir": "EXTRACTED_DATA_DIR",
        "model_artifacts_dir": "MODEL_ARTIFACTS_DIR",
        "postgres_user": "POSTGRES_USER",
        "postgres_password": "POSTGRES_PASSWORD",
        "postgres_app_user": "POSTGRES_APP_USER",
        "postgres_app_password": "POSTGRES_APP_PASSWORD",
        "postgres_db": "POSTGRES_DB",
        "postgres_host": "POSTGRES_HOST",
        "postgres_port": "POSTGRES_PORT",
        "check_interval": "CHECK_INTERVAL",
        "auth_header_user": "AUTH_HEADER_USER",
        "auth_header_sub": "AUTH_HEADER_SUB",
        "auth_header_email": "AUTH_HEADER_EMAIL",
        "auth_header_groups": "AUTH_HEADER_GROUPS",
        "auth_header_preferred_username": "AUTH_HEADER_PREFERRED_USERNAME",
        "auth_header_uid": "AUTH_HEADER_UID",
        "auth_header_gids": "AUTH_HEADER_GIDS",
        "auth_proxy_secret": "AUTH_PROXY_SECRET",
        "auth_local_enabled": "AUTH_LOCAL_ENABLED",
        "auth_proxy_enabled": "AUTH_PROXY_ENABLED",
        "auth_dev_enabled": "AUTH_DEV_ENABLED",
        "auth_session_cookie_name": "AUTH_SESSION_COOKIE_NAME",
        "auth_session_idle_ttl_seconds": "AUTH_SESSION_IDLE_TTL_SECONDS",
        "auth_session_absolute_ttl_seconds": "AUTH_SESSION_ABSOLUTE_TTL_SECONDS",
        "auth_session_secure_cookie": "AUTH_SESSION_SECURE_COOKIE",
        "auth_csrf_cookie_name": "AUTH_CSRF_COOKIE_NAME",
        "auth_csrf_header_name": "AUTH_CSRF_HEADER_NAME",
        "auth_password_min_length": "AUTH_PASSWORD_MIN_LENGTH",
        "auth_password_reject_common": "AUTH_PASSWORD_REJECT_COMMON",
        "auth_login_throttle_enabled": "AUTH_LOGIN_THROTTLE_ENABLED",
        "auth_login_max_attempts": "AUTH_LOGIN_MAX_ATTEMPTS",
        "auth_login_window_seconds": "AUTH_LOGIN_WINDOW_SECONDS",
        "auth_login_lockout_seconds": "AUTH_LOGIN_LOCKOUT_SECONDS",
        "auth_dev_username": "AUTH_DEV_USERNAME",
        "auth_dev_sub": "AUTH_DEV_SUB",
        "auth_dev_email": "AUTH_DEV_EMAIL",
        "auth_dev_groups": "AUTH_DEV_GROUPS_STR",
        "auth_dev_groups_str": "AUTH_DEV_GROUPS_STR",
        "auth_bootstrap_admin_username": "AUTH_BOOTSTRAP_ADMIN_USERNAME",
        "auth_bootstrap_admin_password": "AUTH_BOOTSTRAP_ADMIN_PASSWORD",
        "auth_bootstrap_admin_email": "AUTH_BOOTSTRAP_ADMIN_EMAIL",
        "auth_bootstrap_admin_display_name": "AUTH_BOOTSTRAP_ADMIN_DISPLAY_NAME",
        "acl_enabled": "ACL_ENABLED",
        "embedding_api_base": "EMBEDDING_API_BASE",
        "embedding_api_key": "EMBEDDING_API_KEY",
        "embedding_model": "EMBEDDING_MODEL",
        "embedding_vector_size": "EMBEDDING_VECTOR_SIZE",
        "embedding_max_tokens": "EMBEDDING_MAX_TOKENS",
        "embedding_timeout_seconds": "EMBEDDING_TIMEOUT_SECONDS",
        "embedding_max_concurrent_requests": "EMBEDDING_MAX_CONCURRENT_REQUESTS",
        "ai_backpressure_wait_seconds": "AI_BACKPRESSURE_WAIT_SECONDS",
        "ai_client_max_retries": "AI_CLIENT_MAX_RETRIES",
        "chat_api_base": "CHAT_API_BASE",
        "chat_api_key": "CHAT_API_KEY",
        "chat_model": "CHAT_MODEL",
        "chat_timeout_seconds": "CHAT_TIMEOUT_SECONDS",
        "chat_max_concurrent_requests": "CHAT_MAX_CONCURRENT_REQUESTS",
        "chat_system_prompt": "CHAT_SYSTEM_PROMPT",
        "chat_tool_prompt": "CHAT_TOOL_PROMPT",
        "chat_search_limit": "CHAT_SEARCH_LIMIT",
        "chat_document_max_chars": "CHAT_DOCUMENT_MAX_CHARS",
        "valkey_url": "VALKEY_URL",
        "chat_runner_enabled": "CHAT_RUNNER_ENABLED",
        "chat_run_event_ttl_seconds": "CHAT_RUN_EVENT_TTL_SECONDS",
        "chat_run_claim_timeout_seconds": "CHAT_RUN_CLAIM_TIMEOUT_SECONDS",
        "chat_run_heartbeat_seconds": "CHAT_RUN_HEARTBEAT_SECONDS",
        "chat_run_poll_interval_seconds": "CHAT_RUN_POLL_INTERVAL_SECONDS",
        "chat_run_max_replay_events": "CHAT_RUN_MAX_REPLAY_EVENTS",
        "research_runner_enabled": "RESEARCH_RUNNER_ENABLED",
        "user_event_ttl_seconds": "USER_EVENT_TTL_SECONDS",
        "user_event_max_replay_events": "USER_EVENT_MAX_REPLAY_EVENTS",
        "event_outbox_poll_interval_seconds": "EVENT_OUTBOX_POLL_INTERVAL_SECONDS",
        "picture_description_url": "PICTURE_DESCRIPTION_URL",
        "picture_description_model": "PICTURE_DESCRIPTION_MODEL",
        "picture_description_prompt": "PICTURE_DESCRIPTION_PROMPT",
        "picture_description_timeout_seconds": "PICTURE_DESCRIPTION_TIMEOUT_SECONDS",
        "picture_description_max_concurrent_requests": "PICTURE_DESCRIPTION_MAX_CONCURRENT_REQUESTS",
        "picture_description_max_tokens": "PICTURE_DESCRIPTION_MAX_TOKENS",
        "picture_description_enable_thinking": "PICTURE_DESCRIPTION_ENABLE_THINKING",
        "document_classification_enabled": "DOCUMENT_CLASSIFICATION_ENABLED",
        "document_classification_provider": "DOCUMENT_CLASSIFICATION_PROVIDER",
        "document_classification_model": "DOCUMENT_CLASSIFICATION_MODEL",
        "document_classification_labels": "DOCUMENT_CLASSIFICATION_LABELS",
        "document_extraction_enabled": "DOCUMENT_EXTRACTION_ENABLED",
        "document_extraction_model": "DOCUMENT_EXTRACTION_MODEL",
        "document_extraction_llm_model": "DOCUMENT_EXTRACTION_LLM_MODEL",
        "document_extraction_llm_max_output_tokens": "DOCUMENT_EXTRACTION_LLM_MAX_OUTPUT_TOKENS",
        "document_extraction_llm_enable_thinking": "DOCUMENT_EXTRACTION_LLM_ENABLE_THINKING",
        "document_extraction_chunk_strategy": "DOCUMENT_EXTRACTION_CHUNK_STRATEGY",
        "document_extraction_chat_max_retries": "DOCUMENT_EXTRACTION_CHAT_MAX_RETRIES",
        "document_extraction_chat_evidence_required": "DOCUMENT_EXTRACTION_CHAT_EVIDENCE_REQUIRED",
        "document_extraction_chat_full_text_threshold_chars": "DOCUMENT_EXTRACTION_CHAT_FULL_TEXT_THRESHOLD_CHARS",
        "content_enrichment_stage_timeout_seconds": "CONTENT_ENRICHMENT_STAGE_TIMEOUT_SECONDS",
        "content_enrichment_max_concurrent_requests": "CONTENT_ENRICHMENT_MAX_CONCURRENT_REQUESTS",
        "document_extraction_schema_models": "DOCUMENT_EXTRACTION_SCHEMA_MODELS",
        "document_extraction_schemas": "DOCUMENT_EXTRACTION_SCHEMAS",
        "document_extraction_max_chars": "DOCUMENT_EXTRACTION_MAX_CHARS",
        "log_json_format": "LOG_JSON_FORMAT",
        "log_level": "LOG_LEVEL",
        "reconcile_ttl_seconds": "RECONCILE_TTL_SECONDS",
        "max_upload_file_size_bytes": "MAX_UPLOAD_FILE_SIZE_BYTES",
        "max_upload_batch_size_bytes": "MAX_UPLOAD_BATCH_SIZE_BYTES",
        "max_model_artifact_upload_size_bytes": "MAX_MODEL_ARTIFACT_UPLOAD_SIZE_BYTES",
        "worker_embedding_max_texts": "WORKER_EMBEDDING_MAX_TEXTS",
        "worker_embedding_max_text_chars": "WORKER_EMBEDDING_MAX_TEXT_CHARS",
        "worker_embedding_max_total_chars": "WORKER_EMBEDDING_MAX_TOTAL_CHARS",
        "encryption_key": "ENCRYPTION_KEY",
    }

    def __init__(self, settings_cls: type):
        self.settings_cls = settings_cls

    def __call__(self) -> dict[str, Any]:
        config_file = os.environ.get("CONFIG_FILE", "")
        if not config_file:
            return {}

        path = Path(config_file)
        if not path.is_file():
            logger.warning(
                "CONFIG_FILE=%s not found, skipping YAML config", config_file
            )
            return {}

        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            logger.warning("PyYAML not installed, skipping YAML config")
            return {}

        try:
            data = yaml.safe_load(path.read_text()) or {}
        except Exception:
            logger.exception("Failed to parse YAML config file %s", config_file)
            raise

        result: dict[str, Any] = {}

        for yaml_key, value in data.items():
            # Special handling: acl_admin_groups list → ACL_ADMIN_GROUPS_STR string
            if yaml_key == "acl_admin_groups" and isinstance(value, list):
                result["ACL_ADMIN_GROUPS_STR"] = ",".join(str(g) for g in value)
                continue
            if yaml_key == "auth_dev_groups" and isinstance(value, list):
                result["AUTH_DEV_GROUPS_STR"] = ",".join(str(g) for g in value)
                continue

            # Standard field mapping
            field_name = self.FIELD_MAP.get(yaml_key)
            if field_name is not None:
                result[field_name] = value
            else:
                # Try uppercase as-is (allows using env var names directly in YAML)
                result[yaml_key.upper()] = value

        return result


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Runtime environment
    APP_ENV: str = "development"

    # Public base URL the app is reachable at (scheme + host, no trailing slash),
    # e.g. https://dms.example.org. Used to build the API URL workers connect to.
    # An admin-set value in the General settings UI overrides this.
    PUBLIC_BASE_URL: str = ""

    # Encryption (Fernet key for encrypting secrets at rest)
    ENCRYPTION_KEY: str = ""

    # API Security
    CORS_ALLOW_ORIGINS_STR: str = ""
    CORS_ALLOW_METHODS_STR: str = "GET,POST,PUT,DELETE,OPTIONS"
    CORS_ALLOW_HEADERS_STR: str = (
        "Authorization,Content-Type,X-Correlation-ID,X-Proxy-Secret,X-CSRF-Token"
    )

    # File System
    DATA_VOLUME: str = "/data"
    EXTRACTED_DATA_DIR: str = "/extracted"
    MODEL_ARTIFACTS_DIR: str = "/model-artifacts"

    # Database
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_APP_USER: str = "dms_app"
    POSTGRES_APP_PASSWORD: str = "dms_app"
    POSTGRES_DB: str = "intextum_db"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    # Watcher polling defaults
    CHECK_INTERVAL: int = 30

    # OAuth2-Proxy Headers (configurable for different proxy setups)
    AUTH_HEADER_USER: str = "X-Forwarded-User"
    AUTH_HEADER_SUB: str = "X-Forwarded-User"
    AUTH_HEADER_EMAIL: str = "X-Forwarded-Email"
    AUTH_HEADER_GROUPS: str = "X-Forwarded-Groups"
    AUTH_HEADER_PREFERRED_USERNAME: str = "X-Forwarded-Preferred-Username"
    AUTH_HEADER_UID: str = "X-Forwarded-Uid"
    AUTH_HEADER_GIDS: str = "X-Forwarded-Gids"
    AUTH_PROXY_SECRET: str = ""
    AUTH_LOCAL_ENABLED: bool = False
    AUTH_PROXY_ENABLED: bool = True
    AUTH_DEV_ENABLED: bool = False
    AUTH_SESSION_COOKIE_NAME: str = "intextum_session"
    AUTH_SESSION_IDLE_TTL_SECONDS: int = 3600
    AUTH_SESSION_ABSOLUTE_TTL_SECONDS: int = 604800
    AUTH_SESSION_SECURE_COOKIE: bool = False
    AUTH_CSRF_COOKIE_NAME: str = "intextum_csrf"
    AUTH_CSRF_HEADER_NAME: str = "X-CSRF-Token"
    AUTH_PASSWORD_MIN_LENGTH: int = 12
    AUTH_PASSWORD_REJECT_COMMON: bool = True
    AUTH_LOGIN_THROTTLE_ENABLED: bool = True
    AUTH_LOGIN_MAX_ATTEMPTS: int = 5
    AUTH_LOGIN_WINDOW_SECONDS: int = 300
    AUTH_LOGIN_LOCKOUT_SECONDS: int = 900
    AUTH_DEV_USERNAME: str = "dev"
    AUTH_DEV_SUB: str = "dev:local"
    AUTH_DEV_EMAIL: str = "dev@example.invalid"
    AUTH_DEV_GROUPS_STR: str = ""
    AUTH_BOOTSTRAP_ADMIN_USERNAME: str = ""
    AUTH_BOOTSTRAP_ADMIN_PASSWORD: str = ""
    AUTH_BOOTSTRAP_ADMIN_EMAIL: str = ""
    AUTH_BOOTSTRAP_ADMIN_DISPLAY_NAME: str = ""

    # ACL Settings
    ACL_ENABLED: bool = True
    ACL_ADMIN_GROUPS_STR: str = "admins,administrators"

    # Reconciliation TTL (seconds) for non-watched folders
    RECONCILE_TTL_SECONDS: int = 60

    # Upload limits
    MAX_UPLOAD_FILE_SIZE_BYTES: int = 50 * 1024 * 1024
    MAX_UPLOAD_BATCH_SIZE_BYTES: int = 200 * 1024 * 1024
    MAX_MODEL_ARTIFACT_UPLOAD_SIZE_BYTES: int = 512 * 1024 * 1024

    # Query limits
    MAX_CONVERSATION_MESSAGES: int = 500
    MAX_VECTOR_CHUNK_LIMIT: int = 1000
    WORKER_EMBEDDING_MAX_TEXTS: int = 512
    WORKER_EMBEDDING_MAX_TEXT_CHARS: int = 100_000
    WORKER_EMBEDDING_MAX_TOTAL_CHARS: int = 1_000_000

    # Embedding
    EMBEDDING_API_BASE: str = "http://localhost:11434/v1"
    EMBEDDING_API_KEY: str = "ollama"
    EMBEDDING_MODEL: str = "bge-m3"
    EMBEDDING_VECTOR_SIZE: int = 1024
    EMBEDDING_MAX_TOKENS: int = 8192
    EMBEDDING_TIMEOUT_SECONDS: float = 60.0
    EMBEDDING_MAX_CONCURRENT_REQUESTS: int = 8
    AI_BACKPRESSURE_WAIT_SECONDS: float = 0.25
    AI_CLIENT_MAX_RETRIES: int = 1

    # Chat (LLM)
    CHAT_API_BASE: str = "http://localhost:11434/v1"
    CHAT_API_KEY: str = "ollama"
    CHAT_MODEL: str = "qwen3-vl:8b"
    CHAT_TIMEOUT_SECONDS: float = 300.0
    CHAT_MAX_CONCURRENT_REQUESTS: int = 4
    CHAT_SYSTEM_PROMPT: str = (
        "Sie sind ein hilfreicher Assistent für ein Dokumentenmanagement-System.\n"
        "Beantworte Fragen basierend auf den verfugbaren Dokumenten und gib Unsicherheiten klar an.\n"
        "Wenn Informationen in den Dokumenten fehlen, sage das explizit."
    )
    CHAT_TOOL_PROMPT: str = (
        "## Available Tools\n\n"
        "You have these tools to help users with their questions:\n\n"
        "- **search_documents(query)**: Search across all documents for relevant information. "
        "Use this when the user asks a question and you need to find relevant passages. "
        "Results are numbered [1], [2], etc. - always cite them in your answer using these markers.\n\n"
        "- **get_document(file_path)**: Read the full content of a specific document. "
        "Use this when the user wants a summary of a specific file, or you need to read a full document "
        "for in-depth analysis.\n\n"
        "## Citation Rules\n\n"
        "When you use search_documents, each result is labeled [1], [2], etc. "
        "You MUST cite your sources inline using these numbered markers, e.g.:\n"
        '"The policy requires annual review [1] and board approval [3]."\n\n'
        "Always base your answers on the retrieved documents. If no relevant documents are found, say so."
    )
    CHAT_SEARCH_LIMIT: int = 10
    CHAT_DOCUMENT_MAX_CHARS: int = 30000

    # Resumable chat runs
    VALKEY_URL: str = ""
    CHAT_RUNNER_ENABLED: bool = False
    CHAT_RUN_EVENT_TTL_SECONDS: int = 3600
    CHAT_RUN_CLAIM_TIMEOUT_SECONDS: int = 300
    CHAT_RUN_HEARTBEAT_SECONDS: int = 5
    CHAT_RUN_POLL_INTERVAL_SECONDS: float = 1.0
    CHAT_RUN_MAX_REPLAY_EVENTS: int = 1000
    RESEARCH_RUNNER_ENABLED: bool = True
    USER_EVENT_TTL_SECONDS: int = 86400
    USER_EVENT_MAX_REPLAY_EVENTS: int = 1000
    EVENT_OUTBOX_POLL_INTERVAL_SECONDS: float = 2.0

    # Picture Description (VLM)
    PICTURE_DESCRIPTION_URL: str = "http://localhost:11434"
    PICTURE_DESCRIPTION_MODEL: str = "qwen3-vl:8b"
    PICTURE_DESCRIPTION_PROMPT: str = (
        "Describe the image in three sentences. Be concise and accurate."
    )
    PICTURE_DESCRIPTION_TIMEOUT_SECONDS: float = 300.0
    PICTURE_DESCRIPTION_MAX_CONCURRENT_REQUESTS: int = 2
    PICTURE_DESCRIPTION_MAX_TOKENS: int = 512
    PICTURE_DESCRIPTION_ENABLE_THINKING: bool = False
    DOCUMENT_CLASSIFICATION_ENABLED: bool = False
    DOCUMENT_CLASSIFICATION_PROVIDER: str = "gliner2"
    DOCUMENT_CLASSIFICATION_MODEL: str = "fastino/gliner2-multi-v1"
    DOCUMENT_CLASSIFICATION_LABELS: list[dict[str, Any]] = [
        {
            "name": "Permit",
            "description": (
                "Permits, approvals, official notices, file numbers, or regulatory"
                " decisions issued by authorities."
            ),
            "aliases": ["Approval", "Notice"],
        },
        {
            "name": "Planning Document",
            "description": (
                "Planning or design documents that describe a project scope,"
                " measure, or implementation approach."
            ),
            "aliases": ["Planung", "Planning"],
        },
        {
            "name": "Ecological Report",
            "description": (
                "Environmental, ecological, compensation, habitat, or impact"
                " assessment reports."
            ),
            "aliases": ["Umweltbericht", "Gutachten", "Compensation Report"],
        },
        {
            "name": "Contract",
            "description": "Contracts, agreements, offers, or procurement documents.",
            "aliases": ["Vertrag", "Vereinbarung"],
        },
        {
            "name": "Meeting Minutes",
            "description": "Meeting notes, minutes, summaries, or protocol documents.",
            "aliases": ["Protokoll", "Besprechungsnotiz"],
        },
    ]
    DOCUMENT_EXTRACTION_ENABLED: bool = False
    DOCUMENT_EXTRACTION_PROVIDER: str = "langgraph_extract"
    DOCUMENT_EXTRACTION_MODEL: str = "fastino/gliner2-multi-v1"
    DOCUMENT_EXTRACTION_LLM_MODEL: str = "qwen3-vl:8b"
    DOCUMENT_EXTRACTION_LLM_MAX_OUTPUT_TOKENS: int = 16_384
    DOCUMENT_EXTRACTION_LLM_ENABLE_THINKING: bool = False
    DOCUMENT_EXTRACTION_CHUNK_STRATEGY: Literal["full", "selected"] = "full"
    DOCUMENT_EXTRACTION_CHAT_MAX_RETRIES: int = 2
    DOCUMENT_EXTRACTION_CHAT_EVIDENCE_REQUIRED: bool = True
    DOCUMENT_EXTRACTION_CHAT_FULL_TEXT_THRESHOLD_CHARS: int = 20_000
    CONTENT_ENRICHMENT_STAGE_TIMEOUT_SECONDS: float = 300.0
    CONTENT_ENRICHMENT_MAX_CONCURRENT_REQUESTS: int = 2
    DOCUMENT_EXTRACTION_SCHEMA_MODELS: dict[str, str] = {}
    DOCUMENT_EXTRACTION_SCHEMAS: list[dict[str, Any]] = [
        {
            "name": "permit_core",
            "document_class": "Permit",
            "description": "Core regulatory metadata from permit and notice documents.",
            "fields": [
                {
                    "name": "authority",
                    "dtype": "str",
                    "description": "Issuing authority or office",
                },
                {
                    "name": "file_number",
                    "dtype": "str",
                    "description": "Permit, reference, or file number",
                },
                {
                    "name": "project_name",
                    "dtype": "str",
                    "description": "Project or measure name",
                },
                {
                    "name": "parcel_ids",
                    "dtype": "list",
                    "description": "Referenced parcel identifiers",
                },
                {
                    "name": "deadlines",
                    "dtype": "list",
                    "description": "Deadlines, validity periods, or due dates",
                },
                {
                    "name": "obligations",
                    "dtype": "list",
                    "description": "Binding obligations, conditions, or requirements",
                },
            ],
        },
        {
            "name": "ecology_report_core",
            "document_class": "Ecological Report",
            "description": "Key fields from ecological or impact assessment reports.",
            "fields": [
                {
                    "name": "study_area",
                    "dtype": "str",
                    "description": "Area, site, or location under assessment",
                },
                {
                    "name": "species",
                    "dtype": "list",
                    "description": "Species, habitats, or ecological targets mentioned",
                },
                {
                    "name": "measures",
                    "dtype": "list",
                    "description": "Recommended mitigation, compensation, or management measures",
                },
                {
                    "name": "dates",
                    "dtype": "list",
                    "description": "Relevant survey, monitoring, or report dates",
                },
            ],
        },
    ]
    DOCUMENT_EXTRACTION_MAX_CHARS: int = 12000

    # Logging
    LOG_JSON_FORMAT: bool = True
    LOG_LEVEL: str = "INFO"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ACL_ADMIN_GROUPS(self) -> list[str]:
        """Parse comma-separated admin groups string to list."""
        return [g.strip() for g in self.ACL_ADMIN_GROUPS_STR.split(",") if g.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def AUTH_DEV_GROUPS(self) -> list[str]:
        """Parse comma-separated dev groups string to list."""
        return [g.strip() for g in self.AUTH_DEV_GROUPS_STR.split(",") if g.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def CORS_ALLOW_ORIGINS(self) -> list[str]:
        """Parse comma-separated CORS allowlist string to list."""
        return [o.strip() for o in self.CORS_ALLOW_ORIGINS_STR.split(",") if o.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def CORS_ALLOW_METHODS(self) -> list[str]:
        """Parse comma-separated CORS methods string to list."""
        return [m.strip() for m in self.CORS_ALLOW_METHODS_STR.split(",") if m.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def CORS_ALLOW_HEADERS(self) -> list[str]:
        """Parse comma-separated CORS headers string to list."""
        return [h.strip() for h in self.CORS_ALLOW_HEADERS_STR.split(",") if h.strip()]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (
            init_settings,
            YamlSettingsSource(settings_cls),
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def is_production_env(settings: object) -> bool:
    """Return whether settings opt into production-mode validation."""
    app_env = str(getattr(settings, "APP_ENV", "")).strip().lower()
    return app_env in {"prod", "production"}


def collect_production_config_errors(settings: object) -> list[str]:
    """Collect production-only configuration errors without side effects."""
    if not is_production_env(settings):
        return []

    errors: list[str] = []
    cors_origins = list(getattr(settings, "CORS_ALLOW_ORIGINS", []) or [])

    if not cors_origins:
        errors.append("CORS_ALLOW_ORIGINS must be set in production")
    if any(origin.strip() == "*" for origin in cors_origins):
        errors.append("CORS_ALLOW_ORIGINS must not contain '*' in production")

    if bool(getattr(settings, "AUTH_DEV_ENABLED", False)):
        errors.append("AUTH_DEV_ENABLED must be false in production")

    local_enabled = bool(getattr(settings, "AUTH_LOCAL_ENABLED", False))
    proxy_enabled = bool(getattr(settings, "AUTH_PROXY_ENABLED", False))
    if not local_enabled and not proxy_enabled:
        errors.append("At least one authentication provider must be enabled")

    if local_enabled:
        if not str(getattr(settings, "VALKEY_URL", "")).strip():
            errors.append("AUTH_LOCAL_ENABLED requires VALKEY_URL in production")
        if not bool(getattr(settings, "AUTH_SESSION_SECURE_COOKIE", False)):
            errors.append(
                "AUTH_SESSION_SECURE_COOKIE must be true for local auth in production"
            )

    if proxy_enabled and not str(getattr(settings, "AUTH_PROXY_SECRET", "")).strip():
        errors.append("AUTH_PROXY_ENABLED requires AUTH_PROXY_SECRET in production")

    if not str(getattr(settings, "ENCRYPTION_KEY", "")).strip():
        errors.append("ENCRYPTION_KEY must be set in production")

    postgres_password = str(getattr(settings, "POSTGRES_PASSWORD", "")).strip()
    if not postgres_password or postgres_password == "postgres":
        errors.append("POSTGRES_PASSWORD must be set to a non-default value")

    app_password = str(getattr(settings, "POSTGRES_APP_PASSWORD", "")).strip()
    if not app_password or app_password == "dms_app":
        errors.append("POSTGRES_APP_PASSWORD must be set to a non-default value")

    return errors


def validate_production_settings(settings: object) -> None:
    """Raise when production-mode settings are unsafe."""
    errors = collect_production_config_errors(settings)
    if errors:
        formatted_errors = "\n".join(f"- {error}" for error in errors)
        raise RuntimeError(f"Unsafe production configuration:\n{formatted_errors}")
