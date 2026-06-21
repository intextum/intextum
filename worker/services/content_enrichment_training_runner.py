"""Worker runtime helpers for content enrichment adapter training tasks."""

from __future__ import annotations

import json
import logging
import math
import shutil
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import get_settings
from models import (
    WorkerClaimedTask,
    WorkerContentEnrichmentTrainingArtifactUploadResponse,
    WorkerContentEnrichmentTrainingDataset,
)
from services.backend_client import BackendClient

settings = get_settings()

_DEFAULT_EPOCHS = 3
_DEFAULT_BATCH_SIZE = 2
_DEFAULT_EFFECTIVE_BATCH = 8
_DEFAULT_ENCODER_LR = 1e-5
_DEFAULT_TASK_LR = 5e-4
_DEFAULT_LORA_R = 8
_DEFAULT_LORA_ALPHA = 16.0
_DEFAULT_LORA_DROPOUT = 0.0
_DEFAULT_EVAL_STRATEGY = "none"
_DEFAULT_MAX_LEN = 1024


@dataclass(frozen=True)
class TrainingExampleSplit:
    """Train/validation split for one reviewed GLiNER2 dataset."""

    train_examples: list[dict[str, Any]]
    validation_examples: list[dict[str, Any]]


def _classification_validation_payload(
    example: dict[str, Any],
) -> tuple[str, list[str], str] | None:
    output = example.get("output")
    classifications = (
        output.get("classifications") if isinstance(output, dict) else None
    )
    if not isinstance(classifications, list) or not classifications:
        return None
    candidate = classifications[0]
    if not isinstance(candidate, dict):
        return None
    task_name = candidate.get("task")
    if not isinstance(task_name, str) or not task_name.strip():
        task_name = "document_class"
    labels = [
        item
        for item in candidate.get("labels", [])
        if isinstance(item, str) and item.strip()
    ]
    true_label = candidate.get("true_label")
    if not labels or not isinstance(true_label, str) or not true_label.strip():
        return None
    return task_name, labels, true_label.strip()


def _classification_prediction_label(raw_output: Any, task_name: str) -> str | None:
    if not isinstance(raw_output, dict):
        return None
    raw_label = raw_output.get(task_name)
    if isinstance(raw_label, str) and raw_label.strip():
        return raw_label.strip()
    return None


def evaluate_validation_examples(
    *,
    split: TrainingExampleSplit,
    model: Any,
) -> dict[str, object]:
    """Evaluate the trained adapter against the held-out validation examples."""
    if not split.validation_examples:
        return {
            "validation_status": "skipped",
            "validation_reason": "no_validation_examples",
        }

    total = 0
    correct = 0
    for example in split.validation_examples:
        payload = _classification_validation_payload(example)
        text = example.get("input")
        if payload is None or not isinstance(text, str) or not text.strip():
            continue
        task_name, labels, true_label = payload
        prediction = model.classify_text(text, {task_name: labels})
        predicted_label = _classification_prediction_label(prediction, task_name)
        total += 1
        if predicted_label == true_label:
            correct += 1
    if total == 0:
        return {
            "validation_status": "skipped",
            "validation_reason": "no_valid_examples",
        }
    return {
        "validation_status": "completed",
        "validation_accuracy": correct / total,
        "validation_correct_count": correct,
        "validation_example_count": total,
    }


def _training_work_dir(task_id: str) -> Path:
    return Path(settings.WORK_DIR) / "training" / task_id


def build_gliner_training_examples(
    dataset: WorkerContentEnrichmentTrainingDataset,
) -> list[dict[str, Any]]:
    """Convert reviewed dataset exports into GLiNER2 trainer example payloads."""
    examples: list[dict[str, Any]] = []
    for record in dataset.examples:
        if not record.input.strip() or not record.output:
            continue
        examples.append(
            {
                "input": record.input,
                "output": record.output,
            }
        )
    return examples


def split_training_examples(examples: list[dict[str, Any]]) -> TrainingExampleSplit:
    """Build a small deterministic validation split for one training run."""
    if not examples:
        return TrainingExampleSplit(train_examples=[], validation_examples=[])
    if len(examples) == 1:
        return TrainingExampleSplit(
            train_examples=list(examples),
            validation_examples=list(examples),
        )

    validation_count = 1 if len(examples) < 10 else max(1, len(examples) // 10)
    if validation_count >= len(examples):
        validation_count = 1
    train_examples = list(examples[:-validation_count])
    validation_examples = list(examples[-validation_count:])
    if not train_examples:
        train_examples = list(examples)
    return TrainingExampleSplit(
        train_examples=train_examples,
        validation_examples=validation_examples,
    )


def write_training_dataset_files(
    dataset: WorkerContentEnrichmentTrainingDataset,
    *,
    split: TrainingExampleSplit,
    work_dir: Path,
) -> None:
    """Persist training inputs to disk for reproducibility and debugging."""
    work_dir.mkdir(parents=True, exist_ok=True)
    dataset_file = work_dir / "train.jsonl"
    with dataset_file.open("w", encoding="utf-8") as handle:
        for example in split.train_examples:
            handle.write(json.dumps(example, ensure_ascii=False))
            handle.write("\n")

    if split.validation_examples:
        validation_file = work_dir / "validation.jsonl"
        with validation_file.open("w", encoding="utf-8") as handle:
            for example in split.validation_examples:
                handle.write(json.dumps(example, ensure_ascii=False))
                handle.write("\n")

    metadata_file = work_dir / "dataset-metadata.json"
    metadata_file.write_text(
        json.dumps(
            {
                "task_id": dataset.task_id,
                "training_job_id": dataset.training_job_id,
                "registry_model_id": dataset.registry_model_id,
                "target_kind": dataset.target_kind,
                "training_method": dataset.training_method,
                "base_model": dataset.base_model,
                "target_name": dataset.target_name,
                "config_fingerprint": dataset.config_fingerprint,
                "reviewed_example_count": len(dataset.examples),
                "train_example_count": len(split.train_examples),
                "validation_example_count": len(split.validation_examples),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def build_training_config_kwargs(
    dataset: WorkerContentEnrichmentTrainingDataset,
    *,
    output_dir: Path,
    train_example_count: int,
) -> dict[str, Any]:
    """Build a conservative GLiNER2 LoRA training config.

    The current GLiNER2 evaluation path is unstable for our reviewed training exports, so
    adapter jobs train without inline validation and rely on logged train metrics plus manual
    promotion afterward.
    """
    batch_size = max(1, min(_DEFAULT_BATCH_SIZE, train_example_count))
    effective_batch = max(1, min(_DEFAULT_EFFECTIVE_BATCH, train_example_count))
    gradient_accumulation_steps = max(1, math.ceil(effective_batch / batch_size))
    steps_per_epoch = max(
        1, train_example_count // (batch_size * gradient_accumulation_steps)
    )
    logging_steps = steps_per_epoch
    use_fp16 = str(settings.CLASSIFICATION_DEVICE).strip().lower() in {"cuda", "gpu"}
    experiment_name = str(dataset.target_kind)
    if dataset.target_name:
        experiment_name = f"{experiment_name}-{dataset.target_name}"
    return {
        "output_dir": str(output_dir),
        "experiment_name": experiment_name,
        "num_epochs": _DEFAULT_EPOCHS,
        "batch_size": batch_size,
        "gradient_accumulation_steps": gradient_accumulation_steps,
        "max_len": _DEFAULT_MAX_LEN,
        "encoder_lr": _DEFAULT_ENCODER_LR,
        "task_lr": _DEFAULT_TASK_LR,
        "use_lora": True,
        "lora_r": _DEFAULT_LORA_R,
        "lora_alpha": _DEFAULT_LORA_ALPHA,
        "lora_dropout": _DEFAULT_LORA_DROPOUT,
        "lora_target_modules": ["encoder"],
        "save_adapter_only": True,
        "eval_strategy": _DEFAULT_EVAL_STRATEGY,
        "save_best": False,
        "logging_steps": logging_steps,
        "fp16": use_fp16,
        "num_workers": 0,
        "pin_memory": False,
    }


def locate_adapter_dir(output_dir: Path) -> Path:
    """Resolve the final saved adapter directory produced by GLiNER2 training."""
    final_dir = output_dir / "final"
    if final_dir.is_dir():
        return final_dir
    if output_dir.is_dir():
        return output_dir
    raise FileNotFoundError(f"Adapter output directory not found: {output_dir}")


def create_training_artifact_archive(source_dir: Path, archive_path: Path) -> Path:
    """Create one compressed archive containing the trained adapter files."""
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(source_dir, arcname=source_dir.name)
    return archive_path


def _latest_history_metric(
    trainer: Any | None,
    key: str,
    *,
    history_name: str = "train_metrics_history",
) -> float | None:
    history = getattr(trainer, history_name, None)
    if not isinstance(history, list):
        return None
    for item in reversed(history):
        if hasattr(item, key):
            value = getattr(item, key)
        elif isinstance(item, dict):
            value = item.get(key)
        else:
            value = None
        if isinstance(value, (int, float)) and math.isfinite(value):
            return float(value)
    return None


def _trainer_scalar_metric(trainer: Any | None, key: str) -> float | None:
    value = getattr(trainer, key, None)
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def _train_result_metric(train_result: dict[str, Any] | None, key: str) -> float | None:
    if not isinstance(train_result, dict):
        return None
    value = train_result.get(key)
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def collect_training_metrics(
    dataset: WorkerContentEnrichmentTrainingDataset,
    *,
    split: TrainingExampleSplit,
    upload_result: WorkerContentEnrichmentTrainingArtifactUploadResponse,
    validation_metrics: dict[str, object] | None = None,
    trainer: Any | None = None,
    training_duration_seconds: float | None = None,
    train_result: dict[str, Any] | None = None,
) -> dict[str, object]:
    """Build a compact registry metrics payload for one completed training run."""
    metrics: dict[str, object] = {
        "base_model": dataset.base_model,
        "target_kind": dataset.target_kind,
        "training_method": dataset.training_method,
        "reviewed_example_count": len(dataset.examples),
        "train_example_count": len(split.train_examples),
        "validation_example_count": len(split.validation_examples),
        "artifact_size_bytes": upload_result.size,
    }
    if (
        isinstance(training_duration_seconds, (int, float))
        and training_duration_seconds >= 0
    ):
        metrics["training_duration_seconds"] = round(
            float(training_duration_seconds), 3
        )
    best_metric = _trainer_scalar_metric(trainer, "best_metric")
    if best_metric is None:
        best_metric = _train_result_metric(train_result, "best_metric")
    if best_metric is not None:
        metrics["best_metric"] = best_metric
    global_step = _trainer_scalar_metric(trainer, "global_step")
    if global_step is None:
        global_step = _train_result_metric(train_result, "total_steps")
    if global_step is not None:
        metrics["global_step"] = global_step
    epoch = _trainer_scalar_metric(trainer, "epoch")
    if epoch is None:
        epoch = _train_result_metric(train_result, "total_epochs")
    if epoch is not None:
        metrics["epochs_completed"] = epoch
    train_loss = _latest_history_metric(trainer, "loss")
    if train_loss is not None:
        metrics["train_loss"] = train_loss
    eval_loss = _latest_history_metric(
        trainer, "eval_loss", history_name="eval_metrics_history"
    )
    if eval_loss is not None:
        metrics["eval_loss"] = eval_loss
    samples_per_second = _train_result_metric(train_result, "samples_per_second")
    if samples_per_second is not None:
        metrics["samples_per_second"] = samples_per_second
    total_time_seconds = _train_result_metric(train_result, "total_time_seconds")
    if total_time_seconds is not None:
        metrics["trainer_total_time_seconds"] = total_time_seconds
    if validation_metrics:
        metrics.update(validation_metrics)
    return metrics


def _load_gliner_training_classes():
    from gliner2 import GLiNER2
    from gliner2.training.trainer import GLiNER2Trainer, TrainingConfig

    return GLiNER2, GLiNER2Trainer, TrainingConfig


def execute_content_enrichment_training_task(
    client: BackendClient,
    task: WorkerClaimedTask,
    log: logging.LoggerAdapter,
) -> str:
    """Run one claimed content enrichment training task to completion."""
    dataset = client.get_content_enrichment_training_dataset(
        task.task_id,
        task.task_secret,
    )
    examples = build_gliner_training_examples(dataset)
    if not examples:
        raise ValueError("No reviewed training examples are available for this task")

    split = split_training_examples(examples)
    work_dir = _training_work_dir(task.task_id)
    if work_dir.exists():
        shutil.rmtree(work_dir, ignore_errors=True)
    dataset_dir = work_dir / "dataset"
    output_dir = work_dir / "adapter-output"
    archive_path = work_dir / "adapter.tar.gz"

    write_training_dataset_files(dataset, split=split, work_dir=dataset_dir)

    GLiNER2, GLiNER2Trainer, TrainingConfig = _load_gliner_training_classes()
    config = TrainingConfig(
        **build_training_config_kwargs(
            dataset,
            output_dir=output_dir,
            train_example_count=len(split.train_examples),
        )
    )
    log.info(
        "Starting GLiNER2 adapter training",
        extra={
            "training_job_id": dataset.training_job_id,
            "registry_model_id": dataset.registry_model_id,
            "target_kind": dataset.target_kind,
            "target_name": dataset.target_name,
            "base_model": dataset.base_model,
            "train_example_count": len(split.train_examples),
            "validation_example_count": len(split.validation_examples),
        },
    )
    model = GLiNER2.from_pretrained(dataset.base_model)
    trainer = GLiNER2Trainer(model=model, config=config)
    training_started_at = time.monotonic()
    train_result = trainer.train(
        train_data=split.train_examples,
    )
    training_duration_seconds = time.monotonic() - training_started_at

    adapter_dir = locate_adapter_dir(output_dir)
    validation_metrics: dict[str, object]
    try:
        validation_metrics = evaluate_validation_examples(
            split=split,
            model=model,
        )
    except Exception as exc:
        log.warning(
            "Post-training validation failed",
            extra={
                "training_job_id": dataset.training_job_id,
                "registry_model_id": dataset.registry_model_id,
                "error": str(exc),
            },
        )
        validation_metrics = {
            "validation_status": "failed",
            "validation_error": str(exc),
        }
    create_training_artifact_archive(adapter_dir, archive_path)
    upload_result = client.upload_content_enrichment_training_artifact(
        task.task_id,
        archive_path,
        task.task_secret,
    )
    metrics = collect_training_metrics(
        dataset,
        split=split,
        upload_result=upload_result,
        validation_metrics=validation_metrics,
        trainer=trainer,
        training_duration_seconds=training_duration_seconds,
        train_result=train_result,
    )
    client.complete_content_enrichment_training_task(
        task.task_id,
        task.task_secret,
        artifact_path=upload_result.artifact_path,
        metrics=metrics,
    )
    shutil.rmtree(work_dir, ignore_errors=True)
    return upload_result.artifact_path
