"""Pytest fixtures for backend tests."""

import asyncio
import inspect
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

# Add project root to sys.path before any local imports
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("OPENAI_API_KEY", "test")

# Mock DB connections before any imports happen
if os.environ.get("INTEXTUM_TEST_REAL_DB") != "1":
    patch("sqlalchemy.ext.asyncio.create_async_engine").start()

import pytest
from fastapi.testclient import TestClient
from config import LocalFsDataConnector
from models.user import User
from auth.dependencies import get_current_user, require_user
from database import get_db
from services.connector import connector_registry

_HAS_PYTEST_ASYNCIO = False
try:
    import pytest_asyncio  # noqa: F401
except ImportError:
    _HAS_PYTEST_ASYNCIO = False
else:
    _HAS_PYTEST_ASYNCIO = True


def pytest_configure(config):
    """Register asyncio marker when pytest-asyncio is unavailable."""
    if not _HAS_PYTEST_ASYNCIO:
        config.addinivalue_line(
            "markers",
            "asyncio: run async tests with a local event loop fallback",
        )


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem):
    """Fallback coroutine test runner for environments without pytest-asyncio."""
    if _HAS_PYTEST_ASYNCIO or "asyncio" not in pyfuncitem.keywords:
        return None

    test_function = pyfuncitem.obj
    if not inspect.iscoroutinefunction(test_function):
        return None

    test_args = {
        name: pyfuncitem.funcargs[name] for name in pyfuncitem._fixtureinfo.argnames
    }
    asyncio.run(test_function(**test_args))
    return True


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture(autouse=True)
def reset_source_runtime_cache():
    """Isolate in-process source cache between tests."""
    connector_registry.clear()
    yield
    connector_registry.clear()


@pytest.fixture
def populated_data_dir(temp_data_dir):
    """Create a data directory with test files and folders."""
    folder1 = temp_data_dir / "documents"
    folder1.mkdir()
    (folder1 / "file1.pdf").write_text("pdf content")
    (folder1 / "file2.txt").write_text("text content")

    folder2 = temp_data_dir / "images"
    folder2.mkdir()
    (folder2 / "image1.jpg").write_bytes(b"\xff\xd8\xff\xe0")
    (folder2 / "image2.png").write_bytes(b"\x89PNG")

    hidden = temp_data_dir / ".hidden"
    hidden.mkdir()
    (hidden / ".hiddenfile").write_text("hidden")

    (temp_data_dir / "root_file.docx").write_text("docx content")

    return temp_data_dir


@pytest.fixture
def mock_settings(temp_data_dir):
    """Mock settings with test values."""

    class _Settings:
        def __init__(self, base_dir: Path):
            self.TEST_DATA_ROOT = base_dir
            self.EMBEDDING_API_BASE = "http://localhost:11434/v1"
            self.EMBEDDING_API_KEY = "test-embedding-key"
            self.EMBEDDING_MODEL = "test-embedding-model"
            self.EMBEDDING_VECTOR_SIZE = 1024
            self.EMBEDDING_TIMEOUT_SECONDS = 60.0
            self.EMBEDDING_MAX_CONCURRENT_REQUESTS = 8
            self.AI_BACKPRESSURE_WAIT_SECONDS = 0.25
            self.AI_CLIENT_MAX_RETRIES = 1
            self.CHAT_API_BASE = "http://localhost:11434/v1"
            self.CHAT_API_KEY = "test-chat-key"
            self.CHAT_MODEL = "test-chat-model"
            self.CHAT_TIMEOUT_SECONDS = 300.0
            self.CHAT_MAX_CONCURRENT_REQUESTS = 4
            self.CHAT_SYSTEM_PROMPT = "You are a helpful assistant."
            self.CHAT_TOOL_PROMPT = "Use the available tools when needed."
            self.CHAT_SEARCH_LIMIT = 10
            self.CHAT_DOCUMENT_MAX_CHARS = 30000
            self.VALKEY_URL = ""
            self.CHAT_RUNNER_ENABLED = False
            self.CHAT_RUN_EVENT_TTL_SECONDS = 3600
            self.CHAT_RUN_CLAIM_TIMEOUT_SECONDS = 300
            self.CHAT_RUN_HEARTBEAT_SECONDS = 5
            self.CHAT_RUN_POLL_INTERVAL_SECONDS = 1.0
            self.CHAT_RUN_MAX_REPLAY_EVENTS = 1000
            self.RESEARCH_RUNNER_ENABLED = True
            self.USER_EVENT_TTL_SECONDS = 86400
            self.USER_EVENT_MAX_REPLAY_EVENTS = 1000
            self.EVENT_OUTBOX_POLL_INTERVAL_SECONDS = 2.0
            self.PICTURE_DESCRIPTION_URL = "http://localhost:11434"
            self.PICTURE_DESCRIPTION_MODEL = "test-picture-model"
            self.PICTURE_DESCRIPTION_PROMPT = "Describe the image accurately."
            self.PICTURE_DESCRIPTION_TIMEOUT_SECONDS = 300.0
            self.PICTURE_DESCRIPTION_MAX_CONCURRENT_REQUESTS = 2
            self.PICTURE_DESCRIPTION_MAX_TOKENS = 512
            self.PICTURE_DESCRIPTION_ENABLE_THINKING = False
            self.DOCUMENT_CLASSIFICATION_ENABLED = False
            self.DOCUMENT_CLASSIFICATION_PROVIDER = "gliner2"
            self.DOCUMENT_CLASSIFICATION_MODEL = "fastino/gliner2-multi-v1"
            self.DOCUMENT_CLASSIFICATION_LABELS = []
            self.DOCUMENT_EXTRACTION_ENABLED = False
            self.DOCUMENT_EXTRACTION_PROVIDER = "gliner2"
            self.DOCUMENT_EXTRACTION_MODEL = "fastino/gliner2-multi-v1"
            self.DOCUMENT_EXTRACTION_LLM_MODEL = "qwen3-vl:8b"
            self.DOCUMENT_EXTRACTION_LLM_MAX_OUTPUT_TOKENS = 16_384
            self.DOCUMENT_EXTRACTION_LLM_ENABLE_THINKING = False
            self.DOCUMENT_EXTRACTION_CHUNK_STRATEGY = "full"
            self.DOCUMENT_EXTRACTION_CHAT_MAX_RETRIES = 2
            self.DOCUMENT_EXTRACTION_CHAT_EVIDENCE_REQUIRED = True
            self.DOCUMENT_EXTRACTION_CHAT_FULL_TEXT_THRESHOLD_CHARS = 20_000
            self.CONTENT_ENRICHMENT_STAGE_TIMEOUT_SECONDS = 300.0
            self.CONTENT_ENRICHMENT_MAX_CONCURRENT_REQUESTS = 2
            self.DOCUMENT_EXTRACTION_SCHEMA_MODELS = {}
            self.DOCUMENT_EXTRACTION_SCHEMAS = []
            self.DOCUMENT_EXTRACTION_MAX_CHARS = 12000
            self.CORS_ALLOW_ORIGINS = ["http://localhost:5173"]
            self.CORS_ALLOW_ORIGINS_STR = "http://localhost:5173"
            self.AUTH_HEADER_USER = "X-Forwarded-User"
            self.AUTH_HEADER_SUB = "X-Forwarded-Sub"
            self.AUTH_HEADER_EMAIL = "X-Forwarded-Email"
            self.AUTH_HEADER_GROUPS = "X-Forwarded-Groups"
            self.AUTH_HEADER_PREFERRED_USERNAME = "X-Forwarded-Preferred-Username"
            self.AUTH_HEADER_UID = "X-Forwarded-Uid"
            self.AUTH_HEADER_GIDS = "X-Forwarded-Gids"
            self.AUTH_PROXY_SECRET = "test-proxy-secret"
            self.AUTH_LOCAL_ENABLED = False
            self.AUTH_PROXY_ENABLED = True
            self.AUTH_DEV_ENABLED = False
            self.AUTH_SESSION_COOKIE_NAME = "intextum_session"
            self.AUTH_SESSION_IDLE_TTL_SECONDS = 3600
            self.AUTH_SESSION_ABSOLUTE_TTL_SECONDS = 604800
            self.AUTH_SESSION_SECURE_COOKIE = False
            self.AUTH_CSRF_COOKIE_NAME = "intextum_csrf"
            self.AUTH_CSRF_HEADER_NAME = "X-CSRF-Token"
            self.AUTH_PASSWORD_MIN_LENGTH = 12
            self.AUTH_PASSWORD_REJECT_COMMON = True
            self.AUTH_LOGIN_THROTTLE_ENABLED = True
            self.AUTH_LOGIN_MAX_ATTEMPTS = 5
            self.AUTH_LOGIN_WINDOW_SECONDS = 300
            self.AUTH_LOGIN_LOCKOUT_SECONDS = 900
            self.AUTH_DEV_USERNAME = "dev"
            self.AUTH_DEV_SUB = "dev:local"
            self.AUTH_DEV_EMAIL = "dev@example.invalid"
            self.AUTH_DEV_GROUPS = ["admins"]
            self.AUTH_BOOTSTRAP_ADMIN_USERNAME = "admin"
            self.AUTH_BOOTSTRAP_ADMIN_PASSWORD = "correct-horse-battery-staple"
            self.AUTH_BOOTSTRAP_ADMIN_EMAIL = "admin@example.com"
            self.AUTH_BOOTSTRAP_ADMIN_DISPLAY_NAME = "Admin"
            self.ACL_ENABLED = True
            self.ACL_ADMIN_GROUPS = ["admins"]
            self.LOG_JSON_FORMAT = False
            self.LOG_LEVEL = "DEBUG"
            self.DB_DIR = str(base_dir / "db")
            self.MAX_UPLOAD_FILE_SIZE_BYTES = 1024
            self.MAX_UPLOAD_BATCH_SIZE_BYTES = 2048
            self.MAX_MODEL_ARTIFACT_UPLOAD_SIZE_BYTES = 4096
            self.POSTGRES_USER = "test"
            self.POSTGRES_PASSWORD = "test"
            self.POSTGRES_DB = "test"
            self.POSTGRES_HOST = "localhost"
            self.POSTGRES_PORT = 5432
            self.CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
            self.CORS_ALLOW_HEADERS = [
                "Authorization",
                "Content-Type",
                "X-Correlation-ID",
                "X-Proxy-Secret",
            ]
            self.MAX_CONVERSATION_MESSAGES = 500
            self.MAX_VECTOR_CHUNK_LIMIT = 1000
            self.ENCRYPTION_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
            self.EXTRACTED_DATA_DIR = str(base_dir / "extracted")
            self.MODEL_ARTIFACTS_DIR = str(base_dir / "model-artifacts")

        @property
        def DATA_FOLDERS(self):
            return [
                LocalFsDataConnector(
                    uuid="folder-documents",
                    name="documents",
                    path=str(self.TEST_DATA_ROOT / "documents"),
                    watch=True,
                    auto_process_new=True,
                ),
                LocalFsDataConnector(
                    uuid="folder-images",
                    name="images",
                    path=str(self.TEST_DATA_ROOT / "images"),
                    watch=True,
                    auto_process_new=True,
                ),
            ]

    settings = _Settings(temp_data_dir)
    return settings


@pytest.fixture
def mock_get_settings(mock_settings):
    """Patch get_settings to return mock settings."""
    with patch("config.get_settings", return_value=mock_settings):
        yield mock_settings


@pytest.fixture
def runtime_sources(mock_settings):
    """Initialize runtime source cache from fixture settings."""
    connector_registry.set_connectors(list(mock_settings.DATA_FOLDERS))
    return list(mock_settings.DATA_FOLDERS)


@pytest.fixture
def test_user():
    """Create a test user."""
    from models.user import User

    return User(
        username="testuser",
        sub="sub-testuser",
        email="test@example.com",
        groups=["users", "developers"],
        preferred_username="Test User",
    )


@pytest.fixture
def admin_user():
    """Create an admin user."""
    from models.user import User

    return User(
        username="admin",
        sub="sub-admin",
        email="admin@example.com",
        groups=["admins", "users"],
        preferred_username="Admin User",
    )


@pytest.fixture
def test_client(mock_get_settings, populated_data_dir):
    """Create a test client with mocked dependencies."""
    mock_get_settings.TEST_DATA_ROOT = populated_data_dir
    connector_registry.set_connectors(list(mock_get_settings.DATA_FOLDERS))

    mock_watcher = MagicMock()

    # We need to mock the DB session returned by get_db dependency
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    mock_result.scalars.return_value = mock_scalars
    mock_result.scalar_one_or_none.return_value = None
    mock_result.fetchone.return_value = (0, 0)
    mock_db.execute.return_value = mock_result
    mock_db.add = MagicMock()

    async def override_get_db():
        yield mock_db

    test_user = User(username="testuser", sub="sub-testuser", groups=["users"])
    test_user.is_admin = True

    with (
        patch("main._watcher", mock_watcher),
        patch("main.init_db", new_callable=AsyncMock),
        patch("main.init_chat_checkpointer", new_callable=AsyncMock),
        patch("main.close_chat_checkpointer", new_callable=AsyncMock),
        patch("database.get_settings", return_value=mock_get_settings),
        patch("services.content.service.get_settings", return_value=mock_get_settings),
        patch("routers.content.helpers.get_settings", return_value=mock_get_settings),
        patch("routers.content.mutations.get_settings", return_value=mock_get_settings),
        patch(
            "services.permission.get_settings",
            return_value=mock_get_settings,
            create=True,
        ),
        patch("auth.providers.get_settings", return_value=mock_get_settings),
    ):
        from main import app
        import main

        main.settings = mock_get_settings
        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: test_user
        app.dependency_overrides[require_user] = lambda: test_user
        from auth.dependencies import require_admin

        app.dependency_overrides[require_admin] = lambda: test_user

        with TestClient(app, raise_server_exceptions=False) as client:
            yield client

        app.dependency_overrides.clear()
