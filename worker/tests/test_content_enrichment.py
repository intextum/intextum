"""Tests for worker-side GLiNER2 document classification."""

from unittest.mock import MagicMock, patch

from models import WorkerDocumentClassificationLabel
from services.content_enrichment import classify_document


@patch("services.content_enrichment.model_artifacts._load_extractor")
def test_classify_document_uses_gliner2_classification(mock_load_extractor):
    chunk = type(
        "Chunk", (), {"text": "Permit notice for project 1410", "meta": None}
    )()
    extractor = MagicMock()
    extractor.classify_text.return_value = {"document_class": "Permit"}
    mock_load_extractor.return_value = extractor

    result = classify_document(
        "Permit notice for project 1410",
        model_name="fastino/gliner2-multi-v1",
        labels=[WorkerDocumentClassificationLabel(name="Permit")],
        chunks=[chunk],
    )

    assert result.status == "completed"
    assert result.label == "Permit"
    assert len(result.evidence) == 1
    assert result.evidence[0].chunk_index == 0
    assert extractor.classify_text.call_count == 1
    assert extractor.classify_text.call_args.kwargs == {"include_confidence": True}
    first_call_task = extractor.classify_text.call_args_list[0].args[1][
        "document_class"
    ]
    assert first_call_task["labels"] == ["Permit", "No matching document class"]
    assert first_call_task["multi_label"] is False
    assert first_call_task["label_descriptions"] == {
        "No matching document class": (
            "Use this when the document does not clearly match any configured class."
        )
    }


@patch("services.content_enrichment.model_artifacts._load_extractor")
def test_classify_document_preserves_gliner2_confidence(mock_load_extractor):
    extractor = MagicMock()
    extractor.classify_text.return_value = {
        "document_class": "Invoice",
        "document_class_score": 0.87,
    }
    mock_load_extractor.return_value = extractor

    result = classify_document(
        "Invoice 2026-001",
        model_name="fastino/gliner2-multi-v1",
        labels=[WorkerDocumentClassificationLabel(name="Invoice")],
        chunks=[],
    )

    assert result.status == "completed"
    assert result.label == "Invoice"
    assert result.confidence == 0.87


@patch("services.content_enrichment.model_artifacts._load_extractor")
def test_classify_document_sends_descriptions_and_can_choose_second_label(
    mock_load_extractor,
):
    extractor = MagicMock()
    extractor.classify_text.return_value = {
        "document_class": {"label": "Contract", "confidence": 0.76},
    }
    mock_load_extractor.return_value = extractor

    result = classify_document(
        "This agreement is made between Example GmbH and Demo AG.",
        model_name="fastino/gliner2-multi-v1",
        labels=[
            WorkerDocumentClassificationLabel(
                id="class-invoice",
                name="Invoice",
                description="Bills requesting payment for goods or services",
                aliases=["Rechnung"],
            ),
            WorkerDocumentClassificationLabel(
                id="class-contract",
                name="Contract",
                description="Agreements, terms, and legally binding documents",
                aliases=["Vertrag"],
            ),
        ],
        chunks=[],
    )

    task = extractor.classify_text.call_args.args[1]["document_class"]
    assert result.status == "completed"
    assert result.label == "Contract"
    assert result.class_id == "class-contract"
    assert result.confidence == 0.76
    assert task["labels"] == ["Invoice", "Contract", "No matching document class"]
    assert task["label_descriptions"] == {
        "Invoice": "Bills requesting payment for goods or services. Also known as: Rechnung",
        "Contract": "Agreements, terms, and legally binding documents. Also known as: Vertrag",
        "No matching document class": (
            "Use this when the document does not clearly match any configured class."
        ),
    }


@patch("services.content_enrichment.model_artifacts._load_extractor")
def test_classify_document_skips_implicit_other_for_single_class(mock_load_extractor):
    extractor = MagicMock()
    extractor.classify_text.return_value = {
        "document_class": {"label": "No matching document class", "confidence": 0.82},
    }
    mock_load_extractor.return_value = extractor

    result = classify_document(
        "Random meeting notes",
        model_name="fastino/gliner2-multi-v1",
        labels=[WorkerDocumentClassificationLabel(name="Invoice")],
        chunks=[],
    )

    assert result.status == "skipped"
    assert result.label is None
    assert result.confidence == 0.82
    assert (
        result.error
        == "GLiNER2 classification did not select a configured document class"
    )


@patch("services.content_enrichment.model_artifacts._load_extractor")
def test_classify_document_resolves_candidate_confidence(mock_load_extractor):
    extractor = MagicMock()
    extractor.classify_text.return_value = {
        "document_class": [
            {"label": "Permit", "score": 0.24},
            {"label": "Invoice", "score": 0.91},
        ],
    }
    mock_load_extractor.return_value = extractor

    result = classify_document(
        "Invoice 2026-001",
        model_name="fastino/gliner2-multi-v1",
        labels=[
            WorkerDocumentClassificationLabel(name="Permit"),
            WorkerDocumentClassificationLabel(name="Invoice"),
        ],
        chunks=[],
    )

    assert result.status == "completed"
    assert result.label == "Invoice"
    assert result.confidence == 0.91


def test_schema_models_override_keys_by_id_with_name_fallback():
    """schema_models lookup prefers schema.id so renames don't break overrides."""
    from services.content_enrichment.merge import _resolve_extraction_model_name

    # id match takes priority over name.
    assert (
        _resolve_extraction_model_name(
            "default-model",
            schema_id="schema-abc",
            schema_name="Permit",
            schema_models={
                "schema-abc": "registry:by-id",
                "Permit": "registry:by-name",
            },
        )
        == "registry:by-id"
    )

    # Falls back to name when id missing — preserves existing configs.
    assert (
        _resolve_extraction_model_name(
            "default-model",
            schema_id="",
            schema_name="Permit",
            schema_models={"Permit": "registry:by-name"},
        )
        == "registry:by-name"
    )

    # No match anywhere → default.
    assert (
        _resolve_extraction_model_name(
            "default-model",
            schema_id="schema-xyz",
            schema_name="Other",
            schema_models={"schema-abc": "registry:by-id"},
        )
        == "default-model"
    )
