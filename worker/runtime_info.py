"""Worker runtime validation and metadata helpers."""

from __future__ import annotations

import platform
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.util import find_spec
from typing import Any

from version import get_app_version

STARTUP_AT = datetime.now(UTC)


@dataclass(frozen=True)
class RuntimeDependency:
    """One importable package needed by a worker capability."""

    module: str
    reason: str
    requirement_profile: str


def _torch_probe() -> dict[str, Any]:
    """Collect Torch accelerator facts without raising on optional import problems."""
    try:
        # pylint: disable=import-outside-toplevel
        import torch
    except Exception:  # pylint: disable=broad-exception-caught
        return {
            "torch_version": None,
            "torch_mps_available": False,
            "torch_cuda_available": False,
            "torch_cuda_device_count": 0,
        }

    mps_available = False
    try:
        mps_available = bool(torch.backends.mps.is_available())
    except Exception:  # pylint: disable=broad-exception-caught
        mps_available = False

    cuda_available = False
    cuda_device_count = 0
    try:
        cuda_available = bool(torch.cuda.is_available())
        cuda_device_count = int(torch.cuda.device_count()) if cuda_available else 0
    except Exception:  # pylint: disable=broad-exception-caught
        cuda_available = False
        cuda_device_count = 0

    return {
        "torch_version": getattr(torch, "__version__", None),
        "torch_mps_available": mps_available,
        "torch_cuda_available": cuda_available,
        "torch_cuda_device_count": cuda_device_count,
    }


def runtime_profile_for_device(device: str, *, system: str | None = None) -> str:
    """Return the packaging/runtime profile represented by one device setting."""
    normalized = device.strip().lower()
    platform_system = system or platform.system()
    if normalized == "cuda":
        return "cuda"
    if normalized == "mps" and platform_system == "Darwin":
        return "macos-mps"
    return "cpu"


def validate_accelerator(
    device: str,
    *,
    skip_check: bool = False,
    system: str | None = None,
    torch_probe: dict[str, Any] | None = None,
) -> None:
    """Validate configured accelerator availability before polling for work."""
    if skip_check:
        return

    normalized = device.strip().lower()
    platform_system = system or platform.system()

    if normalized == "cpu":
        return

    probe = torch_probe or _torch_probe()

    if normalized == "mps":
        if platform_system != "Darwin":
            raise RuntimeError("CLASSIFICATION_DEVICE=mps requires macOS host runtime")
        if not probe.get("torch_mps_available"):
            raise RuntimeError("CLASSIFICATION_DEVICE=mps requires available Torch MPS")
        return

    if normalized == "cuda":
        if not probe.get("torch_cuda_available"):
            raise RuntimeError(
                "CLASSIFICATION_DEVICE=cuda requires available Torch CUDA"
            )
        return

    raise RuntimeError("CLASSIFICATION_DEVICE must be one of: cpu, mps, cuda")


def runtime_dependencies_for_capabilities(
    capabilities: list[str],
) -> list[RuntimeDependency]:
    """Return import checks required before polling for the given capabilities."""
    normalized = set(capabilities)
    dependencies: list[RuntimeDependency] = []

    if normalized & {"document", "image"}:
        dependencies.append(
            RuntimeDependency(
                module="docling.document_converter",
                reason="document/image processing",
                requirement_profile="document.txt",
            )
        )

    if "video" in normalized:
        dependencies.append(
            RuntimeDependency(
                module="docling.pipeline.asr_pipeline",
                reason="audio ASR for video/audio capability",
                requirement_profile="asr.txt",
            )
        )

    if "training" in normalized:
        dependencies.append(
            RuntimeDependency(
                module="gliner2",
                reason="content enrichment training",
                requirement_profile="content-enrichment.txt",
            )
        )

    return dependencies


def validate_runtime_dependencies(
    capabilities: list[str],
    *,
    module_finder: Callable[[str], Any] = find_spec,
) -> None:
    """Validate capability-specific optional dependencies before polling."""
    missing: list[RuntimeDependency] = []
    for dependency in runtime_dependencies_for_capabilities(capabilities):
        try:
            module_spec = module_finder(dependency.module)
        except (ImportError, ModuleNotFoundError):
            module_spec = None
        if module_spec is None:
            missing.append(dependency)

    if not missing:
        return

    missing_text = "; ".join(
        f"{item.module} ({item.reason}, profile {item.requirement_profile})"
        for item in missing
    )
    raise RuntimeError(
        "Worker environment is missing dependencies for the configured capabilities. "
        f"Missing: {missing_text}. "
        "On macOS host runtimes, run worker/scripts/setup-macos-mps.sh and start via "
        "worker/scripts/run-macos-mps.sh. Note: MP3/WAV/M4A files are claimed via the "
        "'video' capability because that capability covers media processing."
    )


def build_runtime_metadata(settings, capabilities: list[str]) -> dict[str, Any]:
    """Build non-secret worker runtime metadata for backend visibility."""
    probe = _torch_probe()
    device = str(settings.CLASSIFICATION_DEVICE).strip().lower()
    return {
        "app_version": get_app_version(),
        "runtime_profile": runtime_profile_for_device(device),
        "capabilities": capabilities,
        "classification_device": device,
        "python_version": platform.python_version(),
        "platform_system": platform.system(),
        "platform_machine": platform.machine(),
        "platform_release": platform.release(),
        "torch_version": probe["torch_version"],
        "torch_mps_available": probe["torch_mps_available"],
        "torch_cuda_available": probe["torch_cuda_available"],
        "torch_cuda_device_count": probe["torch_cuda_device_count"],
        "docling_ocr_engine": settings.DOCLING_OCR_ENGINE,
        "asr_model": settings.ASR_MODEL,
        "asr_language": settings.ASR_LANGUAGE,
        "work_dir": settings.WORK_DIR,
        "startup_at": STARTUP_AT.isoformat(),
        "executable": sys.executable,
    }
