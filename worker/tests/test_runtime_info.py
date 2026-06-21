"""Tests for worker runtime validation and metadata."""

import os

import pytest

from intextum_worker.main import _resolve_classification_device
from intextum_worker.runtime_info import (
    build_runtime_metadata,
    runtime_dependencies_for_capabilities,
    runtime_profile_for_device,
    validate_accelerator,
    validate_runtime_dependencies,
)


def test_runtime_profile_for_device():
    assert runtime_profile_for_device("cpu", system="Linux") == "cpu"
    assert runtime_profile_for_device("cuda", system="Linux") == "cuda"
    assert runtime_profile_for_device("mps", system="Darwin") == "macos-mps"
    assert runtime_profile_for_device("mps", system="Linux") == "cpu"


def test_validate_accelerator_allows_cpu_without_torch():
    validate_accelerator(
        "cpu",
        system="Linux",
        torch_probe={"torch_cuda_available": False, "torch_mps_available": False},
    )


def test_validate_accelerator_allows_available_mps_on_macos():
    validate_accelerator(
        "mps",
        system="Darwin",
        torch_probe={"torch_mps_available": True},
    )


def test_validate_accelerator_rejects_mps_outside_macos():
    with pytest.raises(RuntimeError, match="requires macOS"):
        validate_accelerator(
            "mps",
            system="Linux",
            torch_probe={"torch_mps_available": True},
        )


def test_validate_accelerator_rejects_unavailable_mps():
    with pytest.raises(RuntimeError, match="requires available Torch MPS"):
        validate_accelerator(
            "mps",
            system="Darwin",
            torch_probe={"torch_mps_available": False},
        )


def test_validate_accelerator_allows_available_cuda():
    validate_accelerator(
        "cuda",
        system="Linux",
        torch_probe={"torch_cuda_available": True},
    )


def test_validate_accelerator_rejects_unavailable_cuda():
    with pytest.raises(RuntimeError, match="requires available Torch CUDA"):
        validate_accelerator(
            "cuda",
            system="Linux",
            torch_probe={"torch_cuda_available": False},
        )


def test_validate_accelerator_skip_check_allows_unavailable_accelerator():
    validate_accelerator("cuda", skip_check=True, system="Linux", torch_probe={})


def test_resolve_classification_device_disables_torchdynamo_on_mps(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.delenv("CLASSIFICATION_DEVICE", raising=False)
    monkeypatch.delenv("PYTORCH_ENABLE_MPS_FALLBACK", raising=False)
    monkeypatch.delenv("TORCHDYNAMO_DISABLE", raising=False)

    device = _resolve_classification_device("mps")

    assert device == "mps"
    assert os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] == "1"
    assert os.environ["TORCHDYNAMO_DISABLE"] == "1"


def test_resolve_classification_device_leaves_torchdynamo_for_cpu(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.delenv("CLASSIFICATION_DEVICE", raising=False)
    monkeypatch.delenv("TORCHDYNAMO_DISABLE", raising=False)

    device = _resolve_classification_device("cpu")

    assert device == "cpu"
    assert "TORCHDYNAMO_DISABLE" not in os.environ


def test_runtime_dependencies_for_video_include_audio_asr():
    dependencies = runtime_dependencies_for_capabilities(["video"])

    assert [dependency.module for dependency in dependencies] == [
        "docling.pipeline.asr_pipeline"
    ]
    assert dependencies[0].requirement_profile == "asr.txt"


def test_runtime_dependencies_for_document_and_image_share_docling_check():
    dependencies = runtime_dependencies_for_capabilities(["document", "image"])

    assert [dependency.module for dependency in dependencies] == [
        "docling.document_converter"
    ]


def test_validate_runtime_dependencies_allows_available_modules():
    checked: list[str] = []

    def module_finder(module: str):
        checked.append(module)
        return object()

    validate_runtime_dependencies(["document", "video"], module_finder=module_finder)

    assert checked == ["docling.document_converter", "docling.pipeline.asr_pipeline"]


def test_validate_runtime_dependencies_reports_missing_audio_asr():
    def module_finder(module: str):
        if module == "docling.pipeline.asr_pipeline":
            return None
        return object()

    with pytest.raises(RuntimeError) as exc_info:
        validate_runtime_dependencies(["video"], module_finder=module_finder)

    message = str(exc_info.value)
    assert "docling.pipeline.asr_pipeline" in message
    assert "MP3/WAV/M4A" in message
    assert "worker/README.md" in message


def test_build_runtime_metadata_omits_secrets_and_includes_runtime_fields(
    mock_settings,
    monkeypatch,
):
    monkeypatch.setattr(
        "intextum_worker.runtime_info._torch_probe",
        lambda: {
            "torch_version": "2.6.0",
            "torch_mps_available": True,
            "torch_cuda_available": False,
            "torch_cuda_device_count": 0,
        },
    )
    mock_settings.CLASSIFICATION_DEVICE = "mps"
    mock_settings.DOCLING_OCR_ENGINE = "ocrmac"
    mock_settings.ASR_MODEL = "whisper_large_v3"
    mock_settings.ASR_LANGUAGE = "de"

    metadata = build_runtime_metadata(mock_settings, ["document"])

    assert metadata["runtime_profile"] in {"cpu", "macos-mps"}
    assert metadata["capabilities"] == ["document"]
    assert metadata["classification_device"] == "mps"
    assert metadata["torch_version"] == "2.6.0"
    assert metadata["docling_ocr_engine"] == "ocrmac"
    assert metadata["asr_model"] == "whisper_large_v3"
    assert metadata["asr_language"] == "de"
    assert "WORKER_TOKEN" not in metadata
    assert "worker_token" not in metadata
