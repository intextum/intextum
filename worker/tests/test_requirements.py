"""Tests for worker dependency profile hygiene."""

from pathlib import Path

REQUIREMENTS_DIR = Path(__file__).parent.parent / "requirements"


def _requirements_text(name: str) -> str:
    return (REQUIREMENTS_DIR / name).read_text(encoding="utf-8")


def test_base_requirements_exclude_test_and_server_only_dependencies():
    base = _requirements_text("base.txt")

    assert "pytest" not in base
    assert "python-multipart" not in base
    assert "httpx" not in base


def test_default_runtime_profiles_include_feature_groups():
    for profile in ("cpu.txt", "cuda.txt", "macos-mps.txt"):
        content = _requirements_text(profile)

        assert "-r base.txt" in content
        assert "-r document.txt" in content
        assert "-r asr.txt" in content
        assert "-r content-enrichment.txt" in content


def test_cpu_document_profile_excludes_heavy_optional_groups():
    content = _requirements_text("cpu-document.txt")

    assert "-r base.txt" in content
    assert "-r document.txt" in content
    assert "asr.txt" not in content
    assert "content-enrichment.txt" not in content


def test_cpu_profiles_do_not_request_nvidia_packages():
    for profile in ("cpu.txt", "cpu-document.txt"):
        content = _requirements_text(profile).lower()

        assert "nvidia-" not in content
        assert "cu12" not in content
