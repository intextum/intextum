"""Focused tests for Docling-specific processor helpers."""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from models import WorkerRuntimeConfig
from processor_docling import chunk_docling_document, maybe_describe_standalone_image


def test_maybe_describe_standalone_image_uses_first_page_image(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    document_dict = {
        "pages": {
            "1": {
                "image": {"uri": "pages/page-1.png"},
            }
        }
    }
    describe_image = MagicMock(return_value="A detailed image description")
    inject_picture = MagicMock()
    log = MagicMock()

    maybe_describe_standalone_image(
        document_dict,
        file_path=tmp_path / "source.png",
        output_dir=output_dir,
        task_id="task-1",
        task_secret="task-secret",
        content_item_id="file-1",
        log=log,
        describe_image=describe_image,
        inject_picture=inject_picture,
    )

    describe_image.assert_called_once_with(
        output_dir / "pages/page-1.png",
        task_id="task-1",
        task_secret="task-secret",
        content_item_id="file-1",
    )
    inject_picture.assert_called_once_with(
        document_dict,
        "pages/page-1.png",
        "A detailed image description",
        page_image={"uri": "pages/page-1.png"},
        page={"image": {"uri": "pages/page-1.png"}},
    )
    assert (
        json.loads((output_dir / "document.json").read_text(encoding="utf-8"))
        == document_dict
    )


def test_maybe_describe_standalone_image_falls_back_to_filename(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    document_dict = {"pages": {}}
    describe_image = MagicMock()
    inject_picture = MagicMock()
    log = MagicMock()

    maybe_describe_standalone_image(
        document_dict,
        file_path=tmp_path / "source.png",
        output_dir=output_dir,
        task_id="task-1",
        task_secret="task-secret",
        content_item_id="file-1",
        log=log,
        describe_image=describe_image,
        inject_picture=inject_picture,
    )

    describe_image.assert_not_called()
    inject_picture.assert_called_once_with(
        document_dict,
        "source.png",
        None,
        page_image=None,
        page=None,
    )


def test_chunk_docling_document_uses_backend_config_and_tokenizer():
    client = MagicMock()
    client.get_config.return_value = WorkerRuntimeConfig(
        embedding_max_tokens=512,
        embedding_model="test-embedding-model",
    )
    tokenizer_cls = MagicMock()

    with patch.dict(
        sys.modules,
        {
            "docling.datamodel.document": MagicMock(),
            "docling.chunking": MagicMock(),
        },
    ):
        mock_doc = MagicMock()
        mock_chunk = MagicMock()
        sys.modules[
            "docling.datamodel.document"
        ].DoclingDocument.model_validate.return_value = mock_doc
        sys.modules[
            "docling.chunking"
        ].HybridChunker.return_value.chunk.return_value = [mock_chunk]

        doc, chunks, embedding_model_name = chunk_docling_document(
            {"pages": {}},
            api_client_factory=lambda: client,
            tokenizer_cls=tokenizer_cls,
            task_id="task-1",
            task_secret="secret-1",
        )

    assert doc is mock_doc
    assert chunks == [mock_chunk]
    assert embedding_model_name == "test-embedding-model"
    tokenizer_cls.assert_called_once_with(
        client=client,
        max_tokens=512,
        task_id="task-1",
        task_secret="secret-1",
    )


def test_chunk_docling_document_preserves_document_shape_before_validation():
    client = MagicMock()
    client.get_config.return_value = WorkerRuntimeConfig(
        embedding_max_tokens=512,
        embedding_model="test-embedding-model",
    )
    tokenizer_cls = MagicMock()
    document_dict = {
        "pictures": [
            {
                "image": {"uri": "table.png"},
                "annotations": [
                    {
                        "kind": "classification",
                        "predicted_classes": [
                            {"class_name": "table", "confidence": 0.9}
                        ],
                    }
                ],
            }
        ]
    }

    with patch.dict(
        sys.modules,
        {
            "docling.datamodel.document": MagicMock(),
            "docling.chunking": MagicMock(),
        },
    ):
        mock_doc = MagicMock()
        sys.modules[
            "docling.datamodel.document"
        ].DoclingDocument.model_validate.return_value = mock_doc
        sys.modules[
            "docling.chunking"
        ].HybridChunker.return_value.chunk.return_value = []
        model_validate = sys.modules[
            "docling.datamodel.document"
        ].DoclingDocument.model_validate

        chunk_docling_document(
            document_dict,
            api_client_factory=lambda: client,
            tokenizer_cls=tokenizer_cls,
            task_id="task-1",
            task_secret="secret-1",
        )

    validated_doc = model_validate.call_args.args[0]
    pic = validated_doc["pictures"][0]
    assert pic["annotations"] == [
        {
            "kind": "classification",
            "predicted_classes": [{"class_name": "table", "confidence": 0.9}],
        }
    ]


def test_chunk_docling_document_requires_positive_embedding_limit():
    client = MagicMock()
    client.get_config.return_value = WorkerRuntimeConfig(
        embedding_max_tokens=0,
        embedding_model="test-embedding-model",
    )

    with (
        patch.dict(
            sys.modules,
            {
                "docling.datamodel.document": MagicMock(),
                "docling.chunking": MagicMock(),
            },
        ),
        pytest.raises(
            ValueError, match="embedding_max_tokens must be a positive integer"
        ),
    ):
        chunk_docling_document(
            {"pages": {}},
            api_client_factory=lambda: client,
            tokenizer_cls=MagicMock(),
            task_id="task-1",
            task_secret="secret-1",
        )
