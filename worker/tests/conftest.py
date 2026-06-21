"""Shared pytest fixtures for worker tests."""

import os
import sys
from importlib.machinery import ModuleSpec
from pathlib import Path
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("WORKER_TOKEN", "test-token")
os.environ.setdefault("API_URL", "http://api:8000")


def mock_module(name):
    """Create a mock module and register it in sys.modules."""
    m = MagicMock()
    m.__spec__ = ModuleSpec(name, None)
    sys.modules[name] = m
    return m


# Mock heavy dependencies before they are imported by app code
mock_module("docling")
mock_module("docling.datamodel")
mock_module("docling.datamodel.document")
mock_module("docling.chunking")
mock_module("docling_core")
mock_module("docling_core.transforms")
mock_module("docling_core.transforms.chunker")
mock_module("docling_core.transforms.chunker.tokenizer")
tokenizer_base_mock = mock_module("docling_core.transforms.chunker.tokenizer.base")
tokenizer_base_mock.BaseTokenizer = object
mock_module("docling_core.types")
mock_module("docling_core.types.doc")
mock_module("docling_core.types.doc.document")
mock_module("docling_core.types.doc.base")
mock_module("docling.document_converter")
mock_module("docling.datamodel.pipeline_options")
mock_module("docling.datamodel.base_models")
mock_module("openai")
mock_module("easyocr")
mock_module("rapidocr_onnxruntime")
mock_module("onnxruntime")
mock_module("transformers")
mock_module("gliner2")
mock_module("PIL")
mock_module("torch")

# Add worker directory to path for imports
worker_dir = Path(__file__).parent.parent
sys.path.insert(0, str(worker_dir))


@pytest.fixture
def mock_settings():
    """Mock settings with test values."""
    settings = MagicMock()
    settings.API_URL = "http://localhost:8000"
    settings.WORKER_TOKEN = "test-token"
    settings.WORK_DIR = "/tmp/worker"
    settings.CAPABILITIES = "document,video,image"
    settings.parsed_capabilities = ["document", "video", "image"]
    settings.POLL_INTERVAL = 5.0
    settings.CUSTOM_FIELD_ID = 1
    settings.CONTENT_ENRICHMENT_STAGE_TIMEOUT_SECONDS = 300.0
    settings.CLASSIFICATION_DEVICE = "cpu"
    settings.KEEP_MODELS_LOADED = False
    settings.DOCLING_THREADS = 2
    settings.DOCLING_OCR_ENGINE = "easyocr"
    settings.ASR_MODEL = "whisper_large_v3"
    settings.ASR_LANGUAGE = "de"
    settings.TASK_HEARTBEAT_INTERVAL_SECONDS = 0
    settings.DOCUMENT_CLASSIFICATION_ENABLED = False
    settings.DOCUMENT_CLASSIFICATION_MODEL = "fastino/gliner2-multi-v1"
    settings.DOCUMENT_CLASSIFICATION_LABELS = []
    settings.DOCUMENT_EXTRACTION_ENABLED = False
    settings.DOCUMENT_EXTRACTION_MODEL = "fastino/gliner2-multi-v1"
    settings.DOCUMENT_EXTRACTION_SCHEMAS = []
    settings.DOCUMENT_EXTRACTION_MAX_CHARS = 12000
    settings.VIDEO_SCENE_THRESHOLD = 0.25
    settings.VIDEO_FALLBACK_INTERVAL_SECONDS = 20
    return settings


@pytest.fixture
def sample_file_metadata():
    """Sample file metadata from watcher."""
    return {
        "size_bytes": 1024,
        "modified_time": 1234567890.0,
        "created_time": 1234567800.0,
        "permissions": "644",
        "owner_id": 1000,
        "group_id": 1000,
        "access_time": 1234567890.0,
        "is_symlink": False,
        "file_extension": ".pdf",
        "content_item_id": "abc123def456",
    }
