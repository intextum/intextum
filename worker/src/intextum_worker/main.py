"""Worker entry point — HTTP poll loop replacing Celery."""

import argparse
import os
import platform
import sys

from intextum_worker.config import get_settings, parse_capabilities
from intextum_worker.logging_config import configure_logging, get_logger
from intextum_worker.models import WorkerRuntimeMetadata
from intextum_worker.runtime_info import (
    build_runtime_metadata,
    validate_accelerator,
    validate_runtime_dependencies,
)


def _build_parser() -> argparse.ArgumentParser:
    """Build command-line parser for worker runtime overrides."""
    parser = argparse.ArgumentParser(description="intextum Worker")
    parser.add_argument(
        "--capabilities",
        type=str,
        default=None,
        help="Comma-separated capabilities, e.g. document,video,image,training",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=None,
        help="Seconds between poll attempts (default: 5)",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default=None,
        help="API URL override (otherwise API_URL or APP_SCHEME/APP_DOMAIN)",
    )
    parser.add_argument(
        "--work-dir",
        type=str,
        default=None,
        help="Local worker directory override",
    )
    parser.add_argument(
        "--classification-device",
        type=str,
        default=None,
        help="Model device override (e.g. cpu, mps, cuda)",
    )
    parser.add_argument(
        "--docling-ocr-engine",
        type=str,
        default=None,
        help="Docling OCR engine override (easyocr, rapidocr, tesseract, tesseract_cli, ocrmac)",
    )
    parser.add_argument(
        "--skip-device-check",
        action="store_true",
        help="Skip startup accelerator validation",
    )
    return parser


def _resolve_api_url(cli_api_url: str | None) -> None:
    """Resolve API_URL from CLI/env/domain and export it for Settings."""
    if cli_api_url:
        os.environ["API_URL"] = cli_api_url
        return

    if os.environ.get("API_URL", "").strip():
        return

    app_domain = os.environ.get("APP_DOMAIN", "").strip()
    if app_domain:
        app_scheme = os.environ.get("APP_SCHEME", "http").strip() or "http"
        os.environ["API_URL"] = f"{app_scheme}://{app_domain}"


def _resolve_work_dir(cli_work_dir: str | None) -> None:
    """Resolve WORK_DIR from CLI/env for consistent worker file layout."""
    if cli_work_dir:
        os.environ["WORK_DIR"] = cli_work_dir
        return

    if not os.environ.get("WORK_DIR", "").strip():
        os.environ["WORK_DIR"] = "/tmp/worker"


def _resolve_classification_device(cli_device: str | None) -> str:
    """Resolve classification device with platform-aware defaults."""
    if cli_device and cli_device.strip():
        device = cli_device.strip()
    elif os.environ.get("CLASSIFICATION_DEVICE", "").strip():
        device = os.environ["CLASSIFICATION_DEVICE"].strip()
    elif platform.system() == "Darwin":
        device = "mps"
    else:
        device = "cpu"

    os.environ["CLASSIFICATION_DEVICE"] = device

    # Keep behavior parity with previous shell script on macOS.
    if platform.system() == "Darwin" and device == "mps":
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")

    return device


def _resolve_docling_ocr_engine(cli_engine: str | None) -> None:
    """Resolve DOCLING_OCR_ENGINE from CLI/env and export it for Settings."""
    if cli_engine and cli_engine.strip():
        os.environ["DOCLING_OCR_ENGINE"] = cli_engine.strip()
        return

    if not os.environ.get("DOCLING_OCR_ENGINE", "").strip():
        os.environ["DOCLING_OCR_ENGINE"] = "easyocr"


def _report_runtime_metadata(settings, capabilities: list[str], logger) -> None:
    """Best-effort runtime metadata report; polling can continue if it fails."""
    metadata = WorkerRuntimeMetadata.model_validate(
        build_runtime_metadata(settings, capabilities)
    )
    try:
        # pylint: disable=import-outside-toplevel
        from intextum_worker.services.api_client import ApiClient

        ApiClient().report_runtime_metadata(metadata)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Failed to report worker runtime metadata: %s", exc)


def main():
    """Main entry point for the worker."""
    parser = _build_parser()
    args = parser.parse_args()

    _resolve_api_url(args.api_url)
    _resolve_work_dir(args.work_dir)
    _resolve_classification_device(args.classification_device)
    _resolve_docling_ocr_engine(args.docling_ocr_engine)

    configure_logging()
    logger = get_logger(__name__)

    settings = get_settings()

    if not settings.WORKER_TOKEN.strip():
        print("Error: WORKER_TOKEN must be set and non-empty", file=sys.stderr)
        sys.exit(1)

    # Capabilities: CLI arg > env var.
    try:
        capabilities = (
            parse_capabilities(args.capabilities)
            if args.capabilities
            else settings.parsed_capabilities
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    poll_interval = args.poll_interval or settings.POLL_INTERVAL

    if not capabilities:
        print("Error: no capabilities specified", file=sys.stderr)
        sys.exit(1)

    try:
        validate_runtime_dependencies(capabilities)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        validate_accelerator(
            settings.CLASSIFICATION_DEVICE,
            skip_check=args.skip_device_check,
        )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    logger.info(
        "Starting intextum worker",
        extra={
            "api_url": settings.API_URL,
            "work_dir": settings.WORK_DIR,
            "classification_device": settings.CLASSIFICATION_DEVICE,
            "docling_ocr_engine": settings.DOCLING_OCR_ENGINE,
            "asr_model": settings.ASR_MODEL,
            "asr_language": settings.ASR_LANGUAGE,
            "docling_threads": settings.DOCLING_THREADS,
            "keep_models_loaded": settings.KEEP_MODELS_LOADED,
            "content_enrichment_stage_timeout_seconds": (
                settings.CONTENT_ENRICHMENT_STAGE_TIMEOUT_SECONDS
            ),
            "capabilities": capabilities,
            "poll_interval_seconds": poll_interval,
        },
    )
    _report_runtime_metadata(settings, capabilities, logger)

    # pylint: disable=import-outside-toplevel
    from intextum_worker.poll_loop import run_poll_loop

    run_poll_loop(capabilities=capabilities, poll_interval=poll_interval)


if __name__ == "__main__":
    main()
