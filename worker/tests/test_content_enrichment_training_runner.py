"""Tests for content enrichment training worker helpers."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from intextum_worker.models import (
    WorkerClaimedTask,
    WorkerContentEnrichmentTrainingArtifactUploadResponse,
    WorkerContentEnrichmentTrainingDataset,
    WorkerContentEnrichmentTrainingExample,
)
from intextum_worker.services.content_enrichment_training_runner import (
    build_gliner_training_examples,
    build_training_config_kwargs,
    execute_content_enrichment_training_task,
    split_training_examples,
)


def _dataset() -> WorkerContentEnrichmentTrainingDataset:
    return WorkerContentEnrichmentTrainingDataset(
        task_id="task-1",
        training_job_id="job-1",
        registry_model_id="model-1",
        target_kind="classification",
        training_method="lora",
        base_model="fastino/gliner2-multi-v1",
        config_fingerprint="fp-1",
        examples=[
            WorkerContentEnrichmentTrainingExample(
                content_item_id="file-1",
                relative_path="docs/one.pdf",
                input="Invoice 1",
                output={
                    "classifications": [
                        {
                            "task": "document_class",
                            "labels": ["Invoice"],
                            "true_label": "Invoice",
                        }
                    ]
                },
                review_status="accepted",
            ),
            WorkerContentEnrichmentTrainingExample(
                content_item_id="file-2",
                relative_path="docs/two.pdf",
                input="Invoice 2",
                output={
                    "classifications": [
                        {
                            "task": "document_class",
                            "labels": ["Invoice"],
                            "true_label": "Invoice",
                        }
                    ]
                },
                review_status="corrected",
            ),
        ],
    )


def test_build_gliner_training_examples_filters_blank_rows():
    dataset = _dataset()
    dataset.examples.append(
        WorkerContentEnrichmentTrainingExample(
            content_item_id="file-3",
            relative_path="docs/three.pdf",
            input="   ",
            output={},
            review_status="accepted",
        )
    )

    examples = build_gliner_training_examples(dataset)

    assert len(examples) == 2
    assert examples[0]["input"] == "Invoice 1"


def test_split_training_examples_keeps_small_validation_tail():
    split = split_training_examples(
        [{"input": "1", "output": {"x": 1}}, {"input": "2", "output": {"x": 2}}]
    )

    assert len(split.train_examples) == 1
    assert len(split.validation_examples) == 1


def test_build_training_config_kwargs_disables_inline_eval_for_worker_runs():
    dataset = _dataset()

    config = build_training_config_kwargs(
        dataset,
        output_dir=Path("/tmp/adapter"),
        train_example_count=2,
    )

    assert config["eval_strategy"] == "none"
    assert config["save_best"] is False


def test_execute_content_enrichment_training_task_runs_end_to_end(tmp_path):
    dataset = _dataset()
    task = WorkerClaimedTask(
        task_id="task-1",
        task_type="train_content_enrichment_model",
        content_kind="training",
        content_item_id="model-1",
        folder_uuid="__system__",
        relative_path="content-enrichment-training/job-1",
        metadata={
            "training_job_id": "job-1",
            "registry_model_id": "model-1",
            "target_kind": "classification",
            "training_method": "lora",
            "base_model": "fastino/gliner2-multi-v1",
            "config_fingerprint": "fp-1",
        },
        task_secret="secret-1",
    )
    client = MagicMock()
    client.get_content_enrichment_training_dataset.return_value = dataset
    client.upload_content_enrichment_training_artifact.return_value = (
        WorkerContentEnrichmentTrainingArtifactUploadResponse(
            status="ok",
            registry_model_id="model-1",
            artifact_path="content-enrichment/model-1/adapter.tar.gz",
            size=123,
        )
    )
    log = MagicMock()

    class FakeTrainingConfig:
        def __init__(self, **kwargs):
            self.output_dir = kwargs["output_dir"]

    class FakeModel:
        @classmethod
        def from_pretrained(cls, model_name: str):
            assert model_name == "fastino/gliner2-multi-v1"
            return cls()

        def classify_text(self, text: str, labels):
            assert labels == {"document_class": ["Invoice"]}
            return {"document_class": "Invoice"}

    class FakeTrainer:
        def __init__(self, model, config):
            self.model = model
            self.config = config
            self.best_metric = 0.91
            self.global_step = 18
            self.epoch = 3
            self.train_metrics_history = [{"loss": 0.42}]
            self.eval_metrics_history = []

        def train(self, *, train_data):
            assert len(train_data) == 1
            final_dir = Path(self.config.output_dir) / "final"
            final_dir.mkdir(parents=True, exist_ok=True)
            (final_dir / "adapter_model.bin").write_bytes(b"adapter")
            return {
                "total_steps": 18,
                "total_epochs": 3,
                "total_time_seconds": 1.25,
                "samples_per_second": 0.9,
                "best_metric": 0.91,
            }

    with (
        patch(
            "intextum_worker.services.content_enrichment_training_runner.settings.WORK_DIR",
            str(tmp_path),
        ),
        patch(
            "intextum_worker.services.content_enrichment_training_runner._load_gliner_training_classes",
            return_value=(FakeModel, FakeTrainer, FakeTrainingConfig),
        ),
    ):
        artifact_path = execute_content_enrichment_training_task(client, task, log)

    assert artifact_path == "content-enrichment/model-1/adapter.tar.gz"
    client.upload_content_enrichment_training_artifact.assert_called_once()
    client.complete_content_enrichment_training_task.assert_called_once()
    metrics = client.complete_content_enrichment_training_task.call_args.kwargs[
        "metrics"
    ]
    assert metrics["reviewed_example_count"] == 2
    assert metrics["artifact_size_bytes"] == 123
    assert metrics["best_metric"] == 0.91
    assert metrics["train_loss"] == 0.42
    assert metrics["global_step"] == 18.0
    assert metrics["epochs_completed"] == 3.0
    assert metrics["training_duration_seconds"] >= 0
    assert metrics["samples_per_second"] == 0.9
    assert metrics["trainer_total_time_seconds"] == 1.25
    assert metrics["validation_status"] == "completed"
    assert metrics["validation_accuracy"] == 1.0


def test_execute_content_enrichment_training_task_keeps_success_when_validation_fails(
    tmp_path,
):
    dataset = _dataset()
    task = WorkerClaimedTask(
        task_id="task-1",
        task_type="train_content_enrichment_model",
        content_kind="training",
        content_item_id="model-1",
        folder_uuid="__system__",
        relative_path="content-enrichment-training/job-1",
        metadata={
            "training_job_id": "job-1",
            "registry_model_id": "model-1",
            "target_kind": "classification",
            "training_method": "lora",
            "base_model": "fastino/gliner2-multi-v1",
            "config_fingerprint": "fp-1",
        },
        task_secret="secret-1",
    )
    client = MagicMock()
    client.get_content_enrichment_training_dataset.return_value = dataset
    client.upload_content_enrichment_training_artifact.return_value = (
        WorkerContentEnrichmentTrainingArtifactUploadResponse(
            status="ok",
            registry_model_id="model-1",
            artifact_path="content-enrichment/model-1/adapter.tar.gz",
            size=123,
        )
    )
    log = MagicMock()

    class FakeTrainingConfig:
        def __init__(self, **kwargs):
            self.output_dir = kwargs["output_dir"]

    class FakeModel:
        @classmethod
        def from_pretrained(cls, model_name: str):
            assert model_name == "fastino/gliner2-multi-v1"
            return cls()

        def classify_text(self, text: str, labels):
            raise RuntimeError("validation boom")

    class FakeTrainer:
        def __init__(self, model, config):
            self.model = model
            self.config = config
            self.train_metrics_history = [{"loss": 0.42}]
            self.eval_metrics_history = []

        def train(self, *, train_data):
            final_dir = Path(self.config.output_dir) / "final"
            final_dir.mkdir(parents=True, exist_ok=True)
            (final_dir / "adapter_model.bin").write_bytes(b"adapter")
            return {"total_steps": 1}

    with (
        patch(
            "intextum_worker.services.content_enrichment_training_runner.settings.WORK_DIR",
            str(tmp_path),
        ),
        patch(
            "intextum_worker.services.content_enrichment_training_runner._load_gliner_training_classes",
            return_value=(FakeModel, FakeTrainer, FakeTrainingConfig),
        ),
    ):
        artifact_path = execute_content_enrichment_training_task(client, task, log)

    assert artifact_path == "content-enrichment/model-1/adapter.tar.gz"
    client.complete_content_enrichment_training_task.assert_called_once()
    metrics = client.complete_content_enrichment_training_task.call_args.kwargs[
        "metrics"
    ]
    assert metrics["validation_status"] == "failed"
    assert metrics["validation_error"] == "validation boom"
