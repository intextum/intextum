"""Tests for worker services."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from intextum_worker.models import CustomConfig, WorkerRuntimeConfig
from intextum_worker.services.docling import (
    _configure_pipeline_options,
    describe_image_via_vlm,
    get_custom_config,
)
from intextum_worker.services.docling_asr import (
    build_asr_options,
    sanitize_track_times,
    set_asr_language,
)
from intextum_worker.services.docling_enrichment import (
    extract_picture_enrichments,
    inject_standalone_image_as_picture,
)
from intextum_worker.services.docling_enrichment import (
    increment_picture_refs as _increment_picture_refs,
)
from intextum_worker.services.vector import push_to_vector


class TestDoclingService:
    def test_configure_pipeline_options(self, mock_settings):
        config = CustomConfig(do_ocr=True, ocr_lang=["eng"])
        mock_client = MagicMock()
        mock_client.get_config.return_value = WorkerRuntimeConfig(
            embedding_max_tokens=512,
            embedding_model="test-embedding-model",
            picture_description_prompt="Describe this image.",
        )
        with (
            patch("intextum_worker.services.docling.settings", mock_settings),
            patch(
                "intextum_worker.services.docling.ApiClient", return_value=mock_client
            ),
            patch(
                "intextum_worker.services.docling.PictureDescriptionApiOptions"
            ) as mock_pic_opts,
        ):
            options = _configure_pipeline_options(
                config,
                task_id="task-1",
                task_secret="task-secret",
                content_item_id="abc123",
            )

        assert options.do_ocr is True
        assert options.do_picture_classification is True
        assert options.do_picture_description is True
        assert options.enable_remote_services is True
        assert options.ocr_options is not None
        call_kwargs = mock_pic_opts.call_args.kwargs
        assert call_kwargs["url"].endswith("/api/worker/vlm/chat/completions")
        assert call_kwargs["headers"]["X-Task-Id"] == "task-1"
        assert call_kwargs["headers"]["X-Task-Secret"] == "task-secret"
        assert call_kwargs["params"]["content_item_id"] == "abc123"
        assert call_kwargs["params"]["max_completion_tokens"] == 512
        assert call_kwargs["timeout"] == 300

    def test_get_custom_config_prefers_processing_config(self):
        config = get_custom_config(
            {
                "processing_config": {
                    "ocr_engine": "rapidocr",
                    "do_ocr": True,
                    "embedding_model": "bge-small",
                }
            }
        )

        assert config.do_ocr is True
        assert "ocr_engine" not in config.model_dump()
        assert "embedding_model" not in config.model_dump()

    @patch("intextum_worker.services.docling.OcrMacOptions")
    def test_configure_pipeline_options_supports_ocrmac(
        self, mock_ocrmac_options, mock_settings
    ):
        mock_settings.DOCLING_OCR_ENGINE = "ocrmac"
        config = CustomConfig()
        mock_ocrmac_instance = MagicMock()
        mock_ocrmac_options.return_value = mock_ocrmac_instance
        mock_client = MagicMock()
        mock_client.get_config.return_value = WorkerRuntimeConfig(
            embedding_max_tokens=512,
            embedding_model="test-embedding-model",
            picture_description_prompt="Describe this image.",
        )

        with (
            patch("intextum_worker.services.docling.settings", mock_settings),
            patch(
                "intextum_worker.services.docling.ApiClient", return_value=mock_client
            ),
            patch("intextum_worker.services.docling.PictureDescriptionApiOptions"),
        ):
            options = _configure_pipeline_options(
                config,
                task_id="task-1",
                task_secret="task-secret",
                content_item_id="abc123",
            )

        mock_ocrmac_options.assert_called_once_with()
        assert options.ocr_options == mock_ocrmac_instance

    @patch("intextum_worker.services.docling.PictureDescriptionApiOptions")
    def test_configure_pipeline_options_normalizes_ocrmac_langs(
        self, _mock_pic_opts, mock_settings
    ):
        mock_settings.DOCLING_OCR_ENGINE = "ocrmac"
        config = CustomConfig(ocr_lang=["de, en", "de-DE"])
        mock_client = MagicMock()
        mock_client.get_config.return_value = WorkerRuntimeConfig(
            embedding_max_tokens=512,
            embedding_model="test-embedding-model",
            picture_description_prompt="Describe this image.",
        )

        with (
            patch("intextum_worker.services.docling.settings", mock_settings),
            patch(
                "intextum_worker.services.docling.ApiClient", return_value=mock_client
            ),
        ):
            options = _configure_pipeline_options(
                config,
                task_id="task-1",
                task_secret="task-secret",
                content_item_id="abc123",
            )

        assert options.ocr_options.lang == ["de-DE", "en-US"]

    @patch("intextum_worker.services.docling.logger.warning")
    @patch("intextum_worker.services.docling.PictureDescriptionApiOptions")
    def test_configure_pipeline_options_ignores_invalid_ocrmac_langs(
        self, _mock_pic_opts, mock_warning, mock_settings
    ):
        mock_settings.DOCLING_OCR_ENGINE = "ocrmac"
        config = CustomConfig(ocr_lang="zz, de")
        mock_client = MagicMock()
        mock_client.get_config.return_value = WorkerRuntimeConfig(
            embedding_max_tokens=512,
            embedding_model="test-embedding-model",
            picture_description_prompt="Describe this image.",
        )

        with (
            patch("intextum_worker.services.docling.settings", mock_settings),
            patch(
                "intextum_worker.services.docling.ApiClient", return_value=mock_client
            ),
        ):
            options = _configure_pipeline_options(
                config,
                task_id="task-1",
                task_secret="task-secret",
                content_item_id="abc123",
            )

        assert options.ocr_options.lang == ["de-DE"]
        mock_warning.assert_called_once()


class TestAsrLanguageConfig:
    def test_sets_language_field_when_available(self):
        class Options:
            language = None

        opts = Options()
        field = set_asr_language(opts, "de")
        assert field == "language"
        assert opts.language == "de"

    def test_falls_back_to_source_language(self):
        class Options:
            source_language = None

        opts = Options()
        field = set_asr_language(opts, "de")
        assert field == "source_language"
        assert opts.source_language == "de"

    def test_returns_none_when_no_supported_field(self):
        class Options:
            pass

        opts = Options()
        field = set_asr_language(opts, "de")
        assert field is None

    def test_auto_language_clears_language_field(self):
        class Options:
            language = "en"

        opts = Options()
        field = set_asr_language(opts, "auto")
        assert field == "language"
        assert opts.language is None


class TestAsrModelSelection:
    def test_uses_mlx_spec_on_mps(self):
        class Specs:
            WHISPER_LARGE_V3 = {"name": "native"}
            WHISPER_LARGE_V3_MLX = {"name": "mlx"}

        model = build_asr_options(Specs, "mps", "whisper_large_v3")
        assert model["name"] == "mlx"

    def test_uses_native_spec_on_non_mps(self):
        class Specs:
            WHISPER_MEDIUM = {"name": "native"}
            WHISPER_MEDIUM_MLX = {"name": "mlx"}

        model = build_asr_options(Specs, "cpu", "whisper_medium")
        assert model["name"] == "native"

    def test_large_v3_falls_back_to_large_for_older_docling(self):
        class Specs:
            WHISPER_LARGE = {"name": "large"}
            WHISPER_LARGE_MLX = {"name": "large-mlx"}

        model = build_asr_options(Specs, "mps", "whisper_large_v3")
        assert model["name"] == "large-mlx"

    def test_rejects_unknown_asr_model(self):
        class Specs:
            WHISPER_TURBO = {"name": "native"}

        try:
            build_asr_options(Specs, "cpu", "whisper_missing")
        except ValueError as exc:
            assert "Unsupported ASR_MODEL" in str(exc)
        else:
            raise AssertionError("Expected unsupported ASR model to fail")


class TestAsrTimestampSanitization:
    def test_returns_none_for_missing_times(self):
        assert sanitize_track_times(None, 1.0) is None

    def test_estimates_missing_end_time_when_fallback_is_available(self):
        start, end = sanitize_track_times(
            None,
            None,
            fallback_start_time=12.0,
            text="one two three four five",
        )
        assert start == 12.0
        assert end > start

    def test_estimates_missing_end_time_from_known_start(self):
        start, end = sanitize_track_times(
            4.0,
            None,
            text="one two three four five",
        )
        assert start == 4.0
        assert end > start

    def test_keeps_valid_times(self):
        assert sanitize_track_times(1.0, 2.0) == (1.0, 2.0)

    def test_adjusts_zero_or_negative_duration(self):
        start, end = sanitize_track_times(108.2, 108.2)
        assert start == 108.2
        assert end > start

        start, end = sanitize_track_times(5.0, 4.0)
        assert start == 5.0
        assert end > start


class TestExtractPictureEnrichments:
    def test_full_enrichment_extraction(self):
        document_dict = {
            "pictures": [
                {
                    "image": {"uri": "fig1.png"},
                    "meta": {
                        "classification": {
                            "predictions": [
                                {"label": "pie_chart", "score": 0.92},
                                {"label": "bar_chart", "score": 0.05},
                            ]
                        },
                        "description": {
                            "text": "A pie chart showing quarterly revenue"
                        },
                    },
                }
            ]
        }
        result = extract_picture_enrichments(document_dict)
        assert result == {
            "fig1.png": {
                "label": "pie_chart",
                "score": 0.92,
                "description": "A pie chart showing quarterly revenue",
            }
        }

    def test_missing_meta(self):
        document_dict = {"pictures": [{"image": {"uri": "img.png"}}]}
        result = extract_picture_enrichments(document_dict)
        assert result == {
            "img.png": {"label": "unknown", "score": 0.0, "description": None}
        }

    def test_classification_without_description(self):
        document_dict = {
            "pictures": [
                {
                    "image": {"uri": "logo.png"},
                    "meta": {
                        "classification": {
                            "predictions": [{"label": "logo", "score": 0.8}]
                        }
                    },
                }
            ]
        }
        result = extract_picture_enrichments(document_dict)
        assert result["logo.png"]["label"] == "logo"
        assert result["logo.png"]["score"] == 0.8
        assert result["logo.png"]["description"] is None

    def test_empty_pictures(self):
        assert extract_picture_enrichments({}) == {}
        assert extract_picture_enrichments({"pictures": []}) == {}

    def test_highest_confidence_prediction_selected(self):
        document_dict = {
            "pictures": [
                {
                    "image": {"uri": "chart.png"},
                    "meta": {
                        "classification": {
                            "predictions": [
                                {"label": "bar_chart", "score": 0.3},
                                {"label": "flow_chart", "score": 0.95},
                                {"label": "natural_image", "score": 0.1},
                            ]
                        }
                    },
                }
            ]
        }
        result = extract_picture_enrichments(document_dict)
        assert result["chart.png"]["label"] == "flow_chart"
        assert result["chart.png"]["score"] == 0.95

    def test_picture_without_uri_is_skipped(self):
        document_dict = {
            "pictures": [
                {"image": {}, "meta": {}},
                {"image": {"uri": "valid.png"}, "meta": {}},
            ]
        }
        result = extract_picture_enrichments(document_dict)
        assert len(result) == 1
        assert "valid.png" in result

    def test_extracts_current_docling_classification_meta(self):
        document_dict = {
            "pictures": [
                {
                    "image": {"uri": "figure.png"},
                    "meta": {
                        "classification": {
                            "predictions": [
                                {
                                    "class_name": "map",
                                    "confidence": 0.88,
                                    "created_by": "DocumentPictureClassifier",
                                }
                            ]
                        }
                    },
                }
            ]
        }

        result = extract_picture_enrichments(document_dict)

        assert result["figure.png"]["label"] == "map"
        assert result["figure.png"]["score"] == 0.88

    def test_extracts_alternate_prediction_shapes(self):
        document_dict = {
            "pictures": [
                {
                    "image": {"uri": "table.png"},
                    "meta": {
                        "classification": {
                            "predicted_classes": [
                                {"name": "table", "probability": 0.77}
                            ]
                        },
                        "description": "Detected table crop.",
                    },
                }
            ]
        }

        result = extract_picture_enrichments(document_dict)

        assert result["table.png"] == {
            "label": "table",
            "score": 0.77,
            "description": "Detected table crop.",
        }


class TestDescribeImageViaVlm:
    @patch("intextum_worker.services.docling.requests.post")
    @patch("intextum_worker.services.docling.ApiClient")
    @patch("intextum_worker.services.docling.settings")
    def test_successful_vlm_call(
        self, mock_settings, mock_api_cls, mock_post, tmp_path
    ):
        mock_settings.API_URL = "http://localhost:8000"
        mock_settings.WORKER_TOKEN = "test-token"

        mock_client = MagicMock()
        mock_client.get_config.return_value = WorkerRuntimeConfig(
            embedding_max_tokens=512,
            embedding_model="test-embedding-model",
            picture_description_model="gpt-4o",
            picture_description_prompt="Describe this image.",
        )
        mock_api_cls.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "A photo of a forest."}}]
        }
        mock_post.return_value = mock_resp

        # Create a tiny test image file
        image_file = tmp_path / "test.jpg"
        image_file.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-data")

        result = describe_image_via_vlm(
            image_file,
            task_id="task-1",
            task_secret="task-secret",
            content_item_id="abc123",
        )

        assert result == "A photo of a forest."
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["content_item_id"] == "abc123"
        assert payload["messages"][0]["content"][0]["type"] == "image_url"
        assert payload["messages"][0]["content"][1]["text"] == "Describe this image."
        assert call_kwargs.kwargs["headers"]["X-Task-Id"] == "task-1"
        assert call_kwargs.kwargs["headers"]["X-Task-Secret"] == "task-secret"
        assert call_kwargs.args[0].endswith("/api/worker/vlm/chat/completions")

    @patch("intextum_worker.services.docling.requests.post")
    @patch("intextum_worker.services.docling.ApiClient")
    @patch("intextum_worker.services.docling.settings")
    def test_png_mime_type(self, mock_settings, mock_api_cls, mock_post, tmp_path):
        mock_settings.API_URL = "http://localhost:8000"
        mock_settings.WORKER_TOKEN = "test-token"

        mock_client = MagicMock()
        mock_client.get_config.return_value = WorkerRuntimeConfig(
            embedding_max_tokens=512,
            embedding_model="test-embedding-model",
            picture_description_model="model",
            picture_description_prompt="Describe.",
        )
        mock_api_cls.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "A diagram."}}]
        }
        mock_post.return_value = mock_resp

        image_file = tmp_path / "test.png"
        image_file.write_bytes(b"\x89PNG\r\n\x1a\nfake-png-data")

        describe_image_via_vlm(
            image_file,
            task_id="task-1",
            task_secret="task-secret",
            content_item_id="abc123",
        )

        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        image_url = payload["messages"][0]["content"][0]["image_url"]["url"]
        assert image_url.startswith("data:image/png;base64,")


class TestIncrementPictureRefs:
    def test_increments_self_ref(self):
        obj = {"self_ref": "#/pictures/0"}
        _increment_picture_refs(obj)
        assert obj["self_ref"] == "#/pictures/1"

    def test_increments_dollar_ref(self):
        obj = {"$ref": "#/pictures/2"}
        _increment_picture_refs(obj)
        assert obj["$ref"] == "#/pictures/3"

    def test_ignores_non_picture_refs(self):
        obj = {"self_ref": "#/texts/0", "$ref": "#/tables/1"}
        _increment_picture_refs(obj)
        assert obj["self_ref"] == "#/texts/0"
        assert obj["$ref"] == "#/tables/1"

    def test_recursive_in_nested_dicts(self):
        obj = {"a": {"b": {"self_ref": "#/pictures/5"}}}
        _increment_picture_refs(obj)
        assert obj["a"]["b"]["self_ref"] == "#/pictures/6"

    def test_recursive_in_lists(self):
        obj = [{"$ref": "#/pictures/0"}, {"$ref": "#/pictures/1"}]
        _increment_picture_refs(obj)
        assert obj[0]["$ref"] == "#/pictures/1"
        assert obj[1]["$ref"] == "#/pictures/2"


class TestVectorService:
    @patch("intextum_worker.services.vector.ApiClient")
    def test_push_to_vector_uses_file_id_for_point_namespace(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.get_embeddings.return_value = [[0.1, 0.2]]
        mock_client_cls.return_value = mock_client
        chunk = SimpleNamespace(text="Chunk text", meta=None)

        push_to_vector(
            "reports/summary.pdf",
            [chunk],
            metadata={"content_item_id": "file-a"},
            folder_uuid="folder-a",
            task_id="task-a",
            task_secret="secret-a",
        )
        first_points = mock_client.upsert_points.call_args.args[0]

        mock_client.upsert_points.reset_mock()
        mock_client.delete_points.reset_mock()

        push_to_vector(
            "reports/summary.pdf",
            [chunk],
            metadata={"content_item_id": "file-b"},
            folder_uuid="folder-b",
            task_id="task-b",
            task_secret="secret-b",
        )
        second_points = mock_client.upsert_points.call_args.args[0]

        assert first_points[0].id != second_points[0].id

    @patch("intextum_worker.services.vector._build_image_uri_map")
    @patch("intextum_worker.services.vector.ApiClient")
    def test_push_to_vector_includes_structured_chunk_fields(
        self, mock_client_cls, mock_image_uri_map
    ):
        mock_client = MagicMock()
        mock_client.get_embeddings.return_value = [[0.1, 0.2]]
        mock_client_cls.return_value = mock_client
        mock_image_uri_map.return_value = {"pic-1": "images/pic-1.png"}

        doc_item = SimpleNamespace(
            self_ref="pic-1",
            prov=[SimpleNamespace(page_no=2), SimpleNamespace(page_no=1)],
        )
        chunk = SimpleNamespace(
            text="Chunk text",
            meta=SimpleNamespace(headings=("Heading 1",), doc_items=[doc_item]),
        )

        push_to_vector(
            "reports/summary.pdf",
            [chunk],
            doc=MagicMock(),
            metadata={"content_item_id": "file-a"},
            folder_uuid="folder-a",
            task_id="task-a",
            task_secret="secret-a",
        )

        points = mock_client.upsert_points.call_args.args[0]
        payload = points[0].payload

        assert payload.file_path == "reports/summary.pdf"
        assert payload.text == "Chunk text"
        assert payload.chunk_index == 0
        assert payload.headings == ["Heading 1"]
        assert payload.page_numbers == [1, 2]
        assert payload.images == ["images/pic-1.png"]
        assert payload.doc_refs == ["pic-1"]
        assert isinstance(payload.index_version, str)
        assert mock_client.upsert_points.call_args.kwargs["metadata"] == {
            "content_item_id": "file-a"
        }
        assert mock_client.delete_points.call_args.kwargs["content_item_id"] == "file-a"

    @patch("intextum_worker.services.vector.ApiClient")
    def test_push_to_vector_passes_metadata_for_client_side_merge(
        self, mock_client_cls
    ):
        mock_client = MagicMock()
        mock_client.get_embeddings.return_value = [[0.1, 0.2]]
        mock_client_cls.return_value = mock_client
        chunk = SimpleNamespace(text="Chunk text", meta=None)

        push_to_vector(
            "reports/summary.pdf",
            [chunk],
            metadata={
                "content_item_id": "file-a",
                "chunk_index": 999,
                "source": "other_source",
                "text": "wrong text",
            },
            folder_uuid="folder-a",
            task_id="task-a",
            task_secret="secret-a",
        )

        points = mock_client.upsert_points.call_args.args[0]
        assert points[0].payload.chunk_index == 0
        assert points[0].payload.source == "file_system"
        assert points[0].payload.text == "Chunk text"
        assert mock_client.upsert_points.call_args.kwargs["metadata"] == {
            "content_item_id": "file-a",
            "chunk_index": 999,
            "source": "other_source",
            "text": "wrong text",
        }
        assert mock_client.delete_points.call_args.kwargs["content_item_id"] == "file-a"


class TestInjectStandaloneImageAsPicture:
    PAGE_IMAGE = {
        "uri": "page_000000.png",
        "mimetype": "image/png",
        "dpi": 144,
        "size": {"width": 1024.0, "height": 768.0},
    }

    PAGE = {
        "page_no": 1,
        "size": {"width": 1024.0, "height": 768.0},
        "image": {
            "uri": "page_000000.png",
            "mimetype": "image/png",
            "dpi": 144,
            "size": {"width": 1024.0, "height": 768.0},
        },
    }

    def test_inject_with_description(self):
        doc = {"body": {"self_ref": "#/body", "children": []}}
        inject_standalone_image_as_picture(
            doc,
            "page_000000.png",
            "A sunset over mountains.",
            page_image=self.PAGE_IMAGE,
            page=self.PAGE,
        )

        assert len(doc["pictures"]) == 1
        pic = doc["pictures"][0]
        assert pic["self_ref"] == "#/pictures/0"
        assert pic["parent"] == {"$ref": "#/body"}
        assert pic["image"]["uri"] == "page_000000.png"
        assert pic["image"]["mimetype"] == "image/png"
        assert pic["image"]["dpi"] == 144
        assert pic["image"]["size"] == {"width": 1024.0, "height": 768.0}
        pred = pic["meta"]["classification"]["predictions"][0]
        assert pred["class_name"] == "natural_image"
        assert pred["confidence"] == 1.0
        assert pic["meta"]["description"]["text"] == "A sunset over mountains."
        assert "annotations" not in pic

    def test_inject_uses_meta_with_description(self):
        doc = {}
        inject_standalone_image_as_picture(doc, "photo.png", "A sunset.")

        pic = doc["pictures"][0]
        assert pic["meta"]["classification"]["predictions"] == [
            {"class_name": "natural_image", "confidence": 1.0}
        ]
        assert pic["meta"]["description"]["text"] == "A sunset."
        assert "annotations" not in pic

    def test_inject_uses_meta_without_description(self):
        doc = {}
        inject_standalone_image_as_picture(doc, "photo.png", None)

        pic = doc["pictures"][0]
        assert pic["meta"]["classification"]["predictions"] == [
            {"class_name": "natural_image", "confidence": 1.0}
        ]
        assert "description" not in pic["meta"]
        assert "annotations" not in pic

    def test_inject_structural_fields(self):
        doc = {}
        inject_standalone_image_as_picture(doc, "photo.png", "desc")

        pic = doc["pictures"][0]
        assert pic["children"] == []
        assert pic["content_layer"] == "body"
        assert pic["label"] == "picture"
        assert pic["captions"] == []
        assert pic["references"] == []
        assert pic["footnotes"] == []

    def test_inject_prov_with_page(self):
        doc = {}
        inject_standalone_image_as_picture(
            doc,
            "page_000000.png",
            None,
            page_image=self.PAGE_IMAGE,
            page=self.PAGE,
        )

        pic = doc["pictures"][0]
        assert "prov" in pic
        assert len(pic["prov"]) == 1
        prov = pic["prov"][0]
        assert prov["page_no"] == 1
        assert prov["bbox"] == {
            "l": 0.0,
            "t": 0.0,
            "r": 1024.0,
            "b": 768.0,
            "coord_origin": "TOPLEFT",
        }
        assert prov["charspan"] == [0, 0]

    def test_inject_prepends_to_body_children(self):
        doc = {"body": {"self_ref": "#/body", "children": [{"$ref": "#/texts/0"}]}}
        inject_standalone_image_as_picture(
            doc,
            "page_000000.png",
            "A photo.",
            page_image=self.PAGE_IMAGE,
            page=self.PAGE,
        )

        assert doc["body"]["children"] == [
            {"$ref": "#/pictures/0"},
            {"$ref": "#/texts/0"},
        ]

    def test_inject_without_body_does_not_crash(self):
        doc = {}
        inject_standalone_image_as_picture(doc, "photo.png", "desc")

        assert len(doc["pictures"]) == 1
        assert "body" not in doc

    def test_inject_without_page_has_no_prov(self):
        doc = {}
        inject_standalone_image_as_picture(doc, "photo.png", "desc")

        pic = doc["pictures"][0]
        assert pic["parent"] == {"$ref": "#/body"}
        assert "prov" not in pic

    def test_inject_without_description(self):
        doc = {}
        inject_standalone_image_as_picture(
            doc,
            "page_000000.png",
            None,
            page_image=self.PAGE_IMAGE,
        )

        assert len(doc["pictures"]) == 1
        pic = doc["pictures"][0]
        assert pic["image"]["uri"] == "page_000000.png"
        assert pic["parent"] == {"$ref": "#/body"}
        assert "description" not in pic["meta"]

    def test_inject_without_page_image(self):
        doc = {}
        inject_standalone_image_as_picture(doc, "photo.png", "desc")

        pic = doc["pictures"][0]
        assert pic["image"] == {"uri": "photo.png"}
        assert "mimetype" not in pic["image"]

    def test_inject_prepends_before_existing_pictures(self):
        doc = {
            "body": {"self_ref": "#/body", "children": [{"$ref": "#/pictures/0"}]},
            "pictures": [
                {
                    "self_ref": "#/pictures/0",
                    "image": {"uri": "existing.png"},
                    "meta": {},
                }
            ],
        }
        inject_standalone_image_as_picture(doc, "full_image.png", "A photo.")

        assert len(doc["pictures"]) == 2
        # Synthetic picture is at index 0
        assert doc["pictures"][0]["image"]["uri"] == "full_image.png"
        assert doc["pictures"][0]["self_ref"] == "#/pictures/0"
        # Existing picture shifted to index 1
        assert doc["pictures"][1]["image"]["uri"] == "existing.png"
        assert doc["pictures"][1]["self_ref"] == "#/pictures/1"
        # body.children: synthetic at 0, existing shifted to 1
        assert doc["body"]["children"] == [
            {"$ref": "#/pictures/0"},
            {"$ref": "#/pictures/1"},
        ]

    def test_inject_reindexes_multiple_existing_pictures(self):
        doc = {
            "body": {
                "self_ref": "#/body",
                "children": [
                    {"$ref": "#/pictures/0"},
                    {"$ref": "#/texts/0"},
                    {"$ref": "#/pictures/1"},
                ],
            },
            "pictures": [
                {"self_ref": "#/pictures/0", "image": {"uri": "logo.png"}, "meta": {}},
                {"self_ref": "#/pictures/1", "image": {"uri": "map.png"}, "meta": {}},
            ],
        }
        inject_standalone_image_as_picture(doc, "full_page.png", "Full page.")

        assert len(doc["pictures"]) == 3
        assert doc["pictures"][0]["self_ref"] == "#/pictures/0"
        assert doc["pictures"][0]["image"]["uri"] == "full_page.png"
        assert doc["pictures"][1]["self_ref"] == "#/pictures/1"
        assert doc["pictures"][1]["image"]["uri"] == "logo.png"
        assert doc["pictures"][2]["self_ref"] == "#/pictures/2"
        assert doc["pictures"][2]["image"]["uri"] == "map.png"
        assert doc["body"]["children"] == [
            {"$ref": "#/pictures/0"},
            {"$ref": "#/pictures/1"},
            {"$ref": "#/texts/0"},
            {"$ref": "#/pictures/2"},
        ]

    def test_inject_then_extract_enrichments_roundtrip(self):
        doc = {}
        inject_standalone_image_as_picture(doc, "photo.png", "A cat sitting on a mat.")

        enrichments = extract_picture_enrichments(doc)

        assert "photo.png" in enrichments
        entry = enrichments["photo.png"]
        assert entry["label"] == "natural_image"
        assert entry["score"] == 1.0
        assert entry["description"] == "A cat sitting on a mat."

    def test_inject_without_description_then_extract(self):
        doc = {}
        inject_standalone_image_as_picture(doc, "photo.png", None)

        enrichments = extract_picture_enrichments(doc)

        assert "photo.png" in enrichments
        entry = enrichments["photo.png"]
        assert entry["label"] == "natural_image"
        assert entry["description"] is None
