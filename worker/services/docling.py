"""Docling orchestration service.

This module is intentionally a thin facade delegating focused concerns to
helper modules.
"""

import base64
import json
import logging
from pathlib import Path

import requests
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    AcceleratorDevice,
    AcceleratorOptions,
    EasyOcrOptions,
    OcrMacOptions,
    PdfPipelineOptions,
    PictureDescriptionApiOptions,
    RapidOcrOptions,
    TableFormerMode,
    TesseractCliOcrOptions,
    TesseractOcrOptions,
)
from docling.document_converter import (
    AsciiDocFormatOption,
    ConversionResult,
    DocumentConverter,
    ExcelFormatOption,
    HTMLFormatOption,
    ImageFormatOption,
    MarkdownFormatOption,
    PdfFormatOption,
    PowerpointFormatOption,
    WordFormatOption,
)

from config import get_settings
from models import CustomConfig
from services.backend_client import BackendClient
from services.docling_asr import (
    run_asr_conversion as run_docling_asr_conversion,
)

logger = logging.getLogger(__name__)
settings = get_settings()

_OCRMAC_SUPPORTED_LANGS = {
    "en-US",
    "fr-FR",
    "it-IT",
    "de-DE",
    "es-ES",
    "pt-BR",
    "zh-Hans",
    "zh-Hant",
    "yue-Hans",
    "yue-Hant",
    "ko-KR",
    "ja-JP",
    "ru-RU",
    "uk-UA",
    "th-TH",
    "vi-VT",
    "ar-SA",
    "ars-SA",
    "tr-TR",
    "id-ID",
    "cs-CZ",
    "da-DK",
    "nl-NL",
    "no-NO",
    "nn-NO",
    "nb-NO",
    "ms-MY",
    "pl-PL",
    "ro-RO",
    "sv-SE",
}
_OCRMAC_SUPPORTED_LOOKUP = {lang.lower(): lang for lang in _OCRMAC_SUPPORTED_LANGS}
_OCRMAC_LANGUAGE_ALIASES = {
    "en": "en-US",
    "fr": "fr-FR",
    "it": "it-IT",
    "de": "de-DE",
    "es": "es-ES",
    "pt": "pt-BR",
    "zh-cn": "zh-Hans",
    "zh-hans": "zh-Hans",
    "zh-tw": "zh-Hant",
    "zh-hant": "zh-Hant",
    "yue-cn": "yue-Hans",
    "yue-hans": "yue-Hans",
    "yue-tw": "yue-Hant",
    "yue-hant": "yue-Hant",
    "ko": "ko-KR",
    "ja": "ja-JP",
    "ru": "ru-RU",
    "uk": "uk-UA",
    "th": "th-TH",
    "vi": "vi-VT",
    "ar": "ar-SA",
    "ars": "ars-SA",
    "tr": "tr-TR",
    "id": "id-ID",
    "cs": "cs-CZ",
    "da": "da-DK",
    "nl": "nl-NL",
    "no": "no-NO",
    "nn": "nn-NO",
    "nb": "nb-NO",
    "ms": "ms-MY",
    "pl": "pl-PL",
    "ro": "ro-RO",
    "sv": "sv-SE",
}


def _split_ocr_lang_values(ocr_lang: str | list[str]) -> list[str]:
    """Split OCR language values into clean tokens.

    Supports either list input or comma-separated strings.
    """
    values = ocr_lang if isinstance(ocr_lang, list) else [ocr_lang]
    tokens: list[str] = []
    for value in values:
        for part in value.split(","):
            token = part.strip().strip("\"'")
            if token:
                tokens.append(token)
    return tokens


def _normalize_ocrmac_langs(ocr_lang: str | list[str]) -> list[str]:
    """Normalize OCRMac language codes to Docling's expected locale format."""
    normalized: list[str] = []
    invalid: list[str] = []

    for token in _split_ocr_lang_values(ocr_lang):
        key = token.replace("_", "-").strip().lower()
        mapped = _OCRMAC_LANGUAGE_ALIASES.get(key) or _OCRMAC_SUPPORTED_LOOKUP.get(key)
        if mapped:
            normalized.append(mapped)
        else:
            invalid.append(token)

    if invalid:
        logger.warning(
            "Ignoring unsupported OCRMac languages: %s",
            ", ".join(sorted(set(invalid))),
        )

    # Preserve order while de-duplicating.
    return list(dict.fromkeys(normalized))


def _normalize_ocr_langs(ocr_engine: str, ocr_lang: str | list[str]) -> list[str]:
    """Normalize OCR language values per OCR engine."""
    if ocr_engine == "ocrmac":
        return _normalize_ocrmac_langs(ocr_lang)
    return _split_ocr_lang_values(ocr_lang)


def get_custom_config(doc_details: dict) -> CustomConfig:
    """Extract custom configuration from custom fields."""
    raw_processing_config = doc_details.get("processing_config")
    if isinstance(raw_processing_config, dict):
        try:
            return CustomConfig(**raw_processing_config)
        except ValueError as exc:
            logger.warning("Invalid processing_config payload: %s", exc)

    custom_fields = doc_details.get("custom_fields", [])
    for field in custom_fields:
        if field.get("field") == settings.CUSTOM_FIELD_ID:
            try:
                value = field.get("value", "{}")
                if not value:
                    return CustomConfig()
                return CustomConfig(**json.loads(value))
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning(
                    "Invalid config in custom field %s: %s",
                    settings.CUSTOM_FIELD_ID,
                    exc,
                )
                return CustomConfig()
    return CustomConfig()


def _build_accelerator_options(
    device_override: str | None = None,
) -> AcceleratorOptions:
    """Build accelerator options from worker settings."""
    device_map = {
        "cuda": AcceleratorDevice.CUDA,
        "mps": AcceleratorDevice.MPS,
        "cpu": AcceleratorDevice.CPU,
    }
    selected_device = device_override or settings.CLASSIFICATION_DEVICE
    accel_device = device_map.get(selected_device, AcceleratorDevice.AUTO)
    return AcceleratorOptions(num_threads=settings.DOCLING_THREADS, device=accel_device)


def _configure_pipeline_options(
    custom_config: CustomConfig,
    *,
    task_id: str,
    task_secret: str,
    content_item_id: str,
) -> PdfPipelineOptions:
    """Configure PDF/Image Docling pipeline options based on custom settings."""
    pipeline_options = PdfPipelineOptions()

    ocr_engine = settings.DOCLING_OCR_ENGINE
    if ocr_engine == "tesseract":
        pipeline_options.ocr_options = TesseractOcrOptions()
    elif ocr_engine == "tesseract_cli":
        pipeline_options.ocr_options = TesseractCliOcrOptions()
    elif ocr_engine == "rapidocr":
        pipeline_options.ocr_options = RapidOcrOptions()
    elif ocr_engine == "ocrmac":
        pipeline_options.ocr_options = OcrMacOptions()
    else:
        pipeline_options.ocr_options = EasyOcrOptions()

    pipeline_options.do_ocr = custom_config.do_ocr
    pipeline_options.do_table_structure = custom_config.do_table_structure
    pipeline_options.ocr_options.force_full_page_ocr = custom_config.force_full_page_ocr

    if custom_config.ocr_lang:
        normalized_langs = _normalize_ocr_langs(ocr_engine, custom_config.ocr_lang)
        if normalized_langs:
            pipeline_options.ocr_options.lang = normalized_langs

    if custom_config.table_structure_mode:
        mode = custom_config.table_structure_mode.lower()
        if mode == "accurate":
            pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE
        elif mode == "fast":
            pipeline_options.table_structure_options.mode = TableFormerMode.FAST

    if custom_config.images_scale:
        pipeline_options.images_scale = custom_config.images_scale

    pipeline_options.generate_page_images = True
    pipeline_options.generate_picture_images = True
    pipeline_options.generate_table_images = True
    pipeline_options.do_picture_classification = True
    pipeline_options.do_picture_description = True
    pipeline_options.enable_remote_services = True

    client = BackendClient()
    config = client.get_config()
    pipeline_options.picture_description_options = PictureDescriptionApiOptions(
        url=f"{settings.BACKEND_URL.rstrip('/')}/api/worker/vlm/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.WORKER_TOKEN}",
            "X-Task-Id": task_id,
            "X-Task-Secret": task_secret,
        },
        params={
            "content_item_id": content_item_id,
            "seed": 42,
            "max_completion_tokens": config.picture_description_max_tokens,
        },
        prompt=config.picture_description_prompt,
        timeout=max(1.0, float(config.picture_description_timeout_seconds)),
    )
    pipeline_options.accelerator_options = _build_accelerator_options()
    return pipeline_options


def run_docling_conversion(
    file_path: Path,
    custom_config: CustomConfig | None = None,
    *,
    task_id: str,
    task_secret: str,
    content_item_id: str,
) -> ConversionResult:
    """Run Docling conversion for PDF/image files."""
    pipeline_options = _configure_pipeline_options(
        custom_config or CustomConfig(),
        task_id=task_id,
        task_secret=task_secret,
        content_item_id=content_item_id,
    )
    doc_converter = DocumentConverter(
        allowed_formats=[
            InputFormat.PDF,
            InputFormat.IMAGE,
            InputFormat.DOCX,
            InputFormat.XLSX,
            InputFormat.PPTX,
            InputFormat.HTML,
            InputFormat.MD,
            InputFormat.ASCIIDOC,
        ],
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            InputFormat.IMAGE: ImageFormatOption(pipeline_options=pipeline_options),
            InputFormat.DOCX: WordFormatOption(pipeline_options=pipeline_options),
            InputFormat.XLSX: ExcelFormatOption(pipeline_options=pipeline_options),
            InputFormat.PPTX: PowerpointFormatOption(pipeline_options=pipeline_options),
            InputFormat.HTML: HTMLFormatOption(pipeline_options=pipeline_options),
            InputFormat.MD: MarkdownFormatOption(pipeline_options=pipeline_options),
            InputFormat.ASCIIDOC: AsciiDocFormatOption(
                pipeline_options=pipeline_options
            ),
        },
    )
    logger.info("Starting Docling conversion for %s", file_path)
    return doc_converter.convert(file_path)


def run_asr_conversion(audio_path: Path):
    """Run Docling ASR conversion for audio files."""
    return run_docling_asr_conversion(
        audio_path,
        classification_device=settings.CLASSIFICATION_DEVICE,
        asr_model=settings.ASR_MODEL,
        asr_language=settings.ASR_LANGUAGE,
        accelerator_options=_build_accelerator_options(),
    )


def describe_image_via_vlm(
    image_path: Path, *, task_id: str, task_secret: str, content_item_id: str
) -> str | None:
    """Call the VLM to describe a standalone image Docling did not classify."""
    client = BackendClient()
    config = client.get_config()

    image_bytes = image_path.read_bytes()
    mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
    b64 = base64.b64encode(image_bytes).decode()

    payload = {
        "content_item_id": content_item_id,
        "seed": 42,
        "max_completion_tokens": config.picture_description_max_tokens,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                    {"type": "text", "text": config.picture_description_prompt},
                ],
            }
        ],
    }

    url = f"{settings.BACKEND_URL.rstrip('/')}/api/worker/vlm/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.WORKER_TOKEN}",
        "X-Task-Id": task_id,
        "X-Task-Secret": task_secret,
        "Content-Type": "application/json",
    }
    resp = requests.post(
        url,
        json=payload,
        headers=headers,
        timeout=max(1.0, float(config.picture_description_timeout_seconds)),
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]
