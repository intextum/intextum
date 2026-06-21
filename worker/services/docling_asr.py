"""ASR helpers for Docling audio conversion."""

from __future__ import annotations

import copy
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class SafeAsrPipeline:
    """ASR pipeline shim that sanitizes invalid segment timestamps.

    Docling MLX occasionally returns segments with end_time == start_time,
    which violates TrackSource validation (end_time must be greater).
    """

    def __new__(cls, pipeline_options):
        # Keep imports local to avoid ASR dependency requirements for non-ASR tasks.
        from docling.pipeline.asr_pipeline import AsrPipeline

        class _PatchedAsrPipeline(AsrPipeline):
            def _build_document(self, conv_res):
                from docling.datamodel.base_models import ConversionStatus
                from docling.utils.profiling import ProfilingScope, TimeRecorder
                from docling_core.types.doc import (
                    ContentLayer,
                    DocItemLabel,
                    DoclingDocument,
                    DocumentOrigin,
                    TrackSource,
                )

                with TimeRecorder(conv_res, "doc_build", scope=ProfilingScope.DOCUMENT):
                    try:
                        conversation = list(
                            self._model.transcribe(Path(conv_res.input.file).resolve())
                        )  # pylint: disable=protected-access
                        transcript_chars = sum(
                            len((item.text or "").strip()) for item in conversation
                        )
                        logger.info(
                            "Docling ASR returned %s segments and %s transcript chars",
                            len(conversation),
                            transcript_chars,
                        )

                        origin = DocumentOrigin(
                            filename=conv_res.input.file.name or "audio.wav",
                            mimetype="audio/x-wav",
                            binary_hash=conv_res.input.document_hash,
                        )
                        conv_res.document = DoclingDocument(
                            name=conv_res.input.file.stem or "audio.wav",
                            origin=origin,
                        )

                        last_end_time = 0.0
                        for citem in conversation:
                            text = (citem.text or "").strip()
                            if not text:
                                continue
                            times = sanitize_track_times(
                                citem.start_time,
                                citem.end_time,
                                fallback_start_time=last_end_time,
                                text=text,
                            )
                            if times is None:
                                continue
                            start_time, end_time = times
                            last_end_time = end_time
                            track = TrackSource(
                                start_time=start_time,
                                end_time=end_time,
                                voice=citem.speaker,
                            )
                            conv_res.document.add_text(
                                label=DocItemLabel.TEXT,
                                text=text,
                                content_layer=ContentLayer.BODY,
                                source=track,
                            )
                        conv_res.status = ConversionStatus.SUCCESS
                    except Exception as exc:  # pylint: disable=broad-exception-caught
                        logger.error("ASR transcription has an error: %s", exc)
                        conv_res.status = ConversionStatus.FAILURE
                return conv_res

        return _PatchedAsrPipeline(pipeline_options)


def sanitize_track_times(
    start_time: float | None,
    end_time: float | None,
    *,
    fallback_start_time: float | None = None,
    text: str | None = None,
) -> tuple[float, float] | None:
    """Return valid (start, end) timestamps for TrackSource, or None if unusable."""
    if start_time is None and fallback_start_time is None:
        return None
    raw_start = start_time if start_time is not None else fallback_start_time
    if raw_start is None:
        return None
    start = float(raw_start)
    if end_time is None:
        # Keep untimed ASR text instead of dropping it. The estimate is only used
        # for preview navigation; the transcript text itself remains authoritative.
        estimated_seconds = max(1.0, len((text or "").split()) / 2.5)
        end = start + estimated_seconds
    else:
        end = float(end_time)
    if end <= start:
        # Preserve segment text while satisfying TrackSource validation.
        end = start + 1e-3
    return start, end


def _normalize_asr_model_name(asr_model: str) -> str:
    """Normalize user-facing ASR model names to docling spec constants."""
    raw = (asr_model or "").strip().lower()
    if not raw:
        raw = "whisper_medium"
    if not raw.startswith("whisper_"):
        raw = f"whisper_{raw}"
    return raw.upper()


def _candidate_asr_model_names(asr_model: str, classification_device: str) -> list[str]:
    """Return preferred docling ASR spec names for the configured runtime."""
    base_name = _normalize_asr_model_name(asr_model)
    explicit_backend = base_name.endswith(("_MLX", "_NATIVE"))
    base_names = [base_name]
    if base_name == "WHISPER_LARGE_V3":
        # Docling versions differ here: recent docs show WHISPER_LARGE_V3,
        # while some releases expose WHISPER_LARGE.
        base_names.append("WHISPER_LARGE")
    elif base_name == "WHISPER_LARGE":
        base_names.append("WHISPER_LARGE_V3")

    candidates: list[str] = []
    for name in base_names:
        if explicit_backend:
            candidates.append(name)
        elif classification_device == "mps":
            candidates.extend([f"{name}_MLX", name])
        else:
            candidates.extend([name, f"{name}_NATIVE"])
    return list(dict.fromkeys(candidates))


def build_asr_options(
    asr_model_specs,
    classification_device: str,
    asr_model: str = "whisper_medium",
):
    """Build ASR model options from settings.

    Generic names like "whisper_medium" automatically select the matching MLX
    spec on Apple Silicon when available. Explicit names such as
    "whisper_turbo_mlx" or "whisper_large_native" are honored as-is.
    """
    attempted = _candidate_asr_model_names(asr_model, classification_device)
    for model_name in attempted:
        if hasattr(asr_model_specs, model_name):
            base_options = getattr(asr_model_specs, model_name)
            logger.info("Using ASR model spec %s", model_name)
            break
    else:
        available = sorted(
            name for name in dir(asr_model_specs) if name.startswith("WHISPER_")
        )
        raise ValueError(
            f"Unsupported ASR_MODEL={asr_model!r}. Tried: {', '.join(attempted)}. "
            f"Available Whisper specs: {', '.join(available)}"
        )
    return copy.deepcopy(base_options)


def set_asr_language(asr_options, language: str) -> str | None:
    """Set ASR language on Docling ASR options with version-tolerant field names."""
    normalized_language = (language or "").strip().lower()
    value = (
        None if normalized_language in {"", "auto", "detect"} else normalized_language
    )
    for field_name in ("language", "source_language", "lang"):
        if hasattr(asr_options, field_name):
            try:
                setattr(asr_options, field_name, value)
                return field_name
            except Exception:  # pylint: disable=broad-exception-caught
                continue
    return None


def run_asr_conversion(
    audio_path: Path,
    *,
    classification_device: str,
    asr_model: str,
    asr_language: str,
    accelerator_options,
):
    """Run Docling ASR pipeline on an audio file."""
    from docling.datamodel import asr_model_specs
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import AsrPipelineOptions
    from docling.document_converter import AudioFormatOption, DocumentConverter

    pipeline_options = AsrPipelineOptions()
    asr_options = build_asr_options(
        asr_model_specs,
        classification_device,
        asr_model,
    )

    language = (asr_language or "").strip().lower()
    if language:
        configured_attr = set_asr_language(asr_options, language)
        if configured_attr:
            logger.info(
                "Configured ASR language to %s via %s", language, configured_attr
            )
            if classification_device != "mps":
                logger.warning(
                    "Docling native Whisper backend may still auto-detect language "
                    "in current versions; use mps/MLX for strict language control."
                )
        else:
            logger.warning(
                "ASR language configuration not supported by this Docling version; "
                "falling back to model auto-detection"
            )

    pipeline_options.asr_options = asr_options
    pipeline_options.accelerator_options = accelerator_options

    converter = DocumentConverter(
        format_options={
            InputFormat.AUDIO: AudioFormatOption(
                pipeline_cls=SafeAsrPipeline,
                pipeline_options=pipeline_options,
            )
        }
    )

    logger.info("Starting Docling ASR conversion for %s", audio_path)
    return converter.convert(audio_path)
