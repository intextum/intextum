"""Tests for the chat-style LangGraph extraction provider."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from intextum_worker.models import (
    WorkerDocumentExtractionSchema,
)
from intextum_worker.services.content_enrichment.langgraph_provider import (
    LANGGRAPH_PROVIDER,
    LangGraphExtractionProvider,
    _focused_repeated_field_chunks,
    _fuzzy_locate,
    _json_schema_response_format_for_batch,
)
from intextum_worker.services.content_enrichment.registry import (
    DocumentExtractionProviderConfig,
)

_SAMPLE_DOC_TEXT = (
    "Notice Approval Compensation\n"
    "Datum: 15. März 2021\n"
    "Titel: Habitat Project Alpha\n"
    "Die unter I. genannte Approval ergeht unter folgenden Nebenbestimmungen:\n"
    "1. Erste Auflage muss erfüllt werden.\n"
    "2. Zweite Auflage betrifft Monitoring.\n"
)


def _schema() -> WorkerDocumentExtractionSchema:
    return WorkerDocumentExtractionSchema.model_validate(
        {
            "id": "schema-1",
            "name": "OfficialNotice",
            "document_class_id": "class-1",
            "document_class": "OfficialNotice",
            "description": "",
            "fields": [
                {
                    "name": "Datum",
                    "dtype": "str",
                    "description": "Date of letter",
                    "required": True,
                    "extraction_mode": "chat",
                    "examples": [],
                    "fields": [],
                },
                {
                    "name": "Titel",
                    "dtype": "str",
                    "description": "Title",
                    "required": False,
                    "extraction_mode": "chat",
                    "examples": [],
                    "fields": [],
                },
                {
                    "name": "Auflagen",
                    "dtype": "object_list",
                    "description": "Numbered Auflagen",
                    "required": False,
                    "extraction_mode": "chat",
                    "fields": [
                        {"name": "Nummer", "dtype": "str", "description": "Number"},
                        {"name": "Text", "dtype": "str", "description": "Body"},
                    ],
                    "examples": [],
                },
            ],
            "scenes": [],
            "version": 1,
        }
    )


def _config() -> DocumentExtractionProviderConfig:
    return DocumentExtractionProviderConfig(
        provider=LANGGRAPH_PROVIDER,
        model_name="qwen3-mock",
        max_chars=12_000,
        task_id="task-1",
        task_secret="secret-1",
        max_output_tokens=8_000,
        chunk_strategy="full",
    )


def _chunks_for_doc(text: str) -> list[SimpleNamespace]:
    """Split the sample doc on blank lines and emit chunk-shaped objects."""
    parts = [part.strip() for part in text.split("\n\n") if part.strip()]
    chunks: list[SimpleNamespace] = []
    for index, part in enumerate(parts):
        chunks.append(
            SimpleNamespace(
                chunk_index=index,
                text=part,
                page_numbers=[1],
                doc_refs=[],
                images=[],
            )
        )
    return chunks


def _fake_openai_response(content: str, finish_reason: str = "stop") -> list[MagicMock]:
    """Return a fake streaming response (iterable of delta chunks).

    Splits the payload into a few chunks so the streaming accumulator path is
    actually exercised by the test, and emits a final chunk that carries the
    ``finish_reason`` per OpenAI's streaming convention.
    """
    # Split content into thirds so streaming logic is exercised.
    if content:
        third = max(1, len(content) // 3)
        pieces = [content[:third], content[third : third * 2], content[third * 2 :]]
        pieces = [piece for piece in pieces if piece]
    else:
        pieces = [""]

    chunks: list[MagicMock] = []
    for piece in pieces:
        delta = MagicMock()
        delta.content = piece
        choice = MagicMock()
        choice.delta = delta
        choice.finish_reason = None
        chunk = MagicMock()
        chunk.choices = [choice]
        chunks.append(chunk)

    final_delta = MagicMock()
    final_delta.content = None
    final_choice = MagicMock()
    final_choice.delta = final_delta
    final_choice.finish_reason = finish_reason
    final_chunk = MagicMock()
    final_chunk.choices = [final_choice]
    chunks.append(final_chunk)
    return chunks


def test_json_schema_response_format_for_batch_is_strict():
    schema = WorkerDocumentExtractionSchema.model_validate(
        {
            "id": "schema-strict",
            "name": "Strict Schema",
            "document_class_id": "class-1",
            "document_class": "Strict",
            "fields": [
                {
                    "name": "Datum",
                    "dtype": "date",
                    "description": "Date",
                    "required": False,
                },
                {
                    "name": "Betrag",
                    "dtype": "currency",
                    "description": "Amount",
                    "required": False,
                },
                {
                    "name": "Tags",
                    "dtype": "list",
                    "description": "Tags",
                    "required": False,
                },
                {
                    "name": "Auflagen",
                    "dtype": "object_list",
                    "description": "Conditions",
                    "required": False,
                    "fields": [
                        {"name": "Nummer", "dtype": "int", "description": "Number"},
                        {"name": "Text", "dtype": "str", "description": "Text"},
                    ],
                },
            ],
        }
    )

    response_format = _json_schema_response_format_for_batch(
        schema, ["Datum", "Betrag", "Tags", "Auflagen"]
    )

    assert response_format["type"] == "json_schema"
    json_schema = response_format["json_schema"]
    assert json_schema["strict"] is True
    root = json_schema["schema"]
    assert root["additionalProperties"] is False
    assert root["required"] == ["Datum", "Betrag", "Tags", "Auflagen"]
    assert root["properties"]["Datum"]["required"] == ["value", "evidence_anchor"]
    assert root["properties"]["Datum"]["properties"]["value"]["type"] == [
        "string",
        "null",
    ]
    currency_value = root["properties"]["Betrag"]["properties"]["value"]
    assert currency_value["additionalProperties"] is False
    assert currency_value["required"] == ["amount", "currency"]
    assert currency_value["properties"]["amount"]["type"] == ["number", "null"]
    assert root["properties"]["Tags"]["items"]["type"] == "string"
    object_item = root["properties"]["Auflagen"]["items"]
    assert object_item["additionalProperties"] is False
    object_value = object_item["properties"]["value"]
    assert object_value["required"] == ["Nummer", "Text"]
    assert object_value["properties"]["Nummer"]["type"] == ["integer", "null"]


def test_full_text_pass_extracts_all_fields_with_evidence():
    schema = _schema()
    config = _config()
    chunks = _chunks_for_doc(_SAMPLE_DOC_TEXT)
    scalar_batch_payload = {
        "Datum": {
            "value": "15. März 2021",
            "evidence_anchor": "Datum: 15. März 2021",
        },
        "Titel": {
            "value": "Habitat Project Alpha",
            "evidence_anchor": "Titel: Habitat Project Alpha",
        },
    }
    object_batch_payload = {
        "Auflagen": [
            {
                "value": {"Nummer": "1", "Text": "Erste Auflage muss erfüllt werden."},
                "evidence_anchor": "1. Erste Auflage muss erfüllt werden.",
            },
            {
                "value": {"Nummer": "2", "Text": "Zweite Auflage betrifft Monitoring."},
                "evidence_anchor": "2. Zweite Auflage betrifft Monitoring.",
            },
        ]
    }
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _fake_openai_response(json.dumps(scalar_batch_payload, ensure_ascii=False)),
        _fake_openai_response(json.dumps(object_batch_payload, ensure_ascii=False)),
    ]
    with (
        patch(
            "intextum_worker.services.content_enrichment.langgraph_provider._build_openai_client",
            return_value=client,
        ),
        patch(
            "intextum_worker.services.content_enrichment.langgraph_provider._runtime_settings",
            return_value=(2, True, 50_000),
        ),
    ):
        result = LangGraphExtractionProvider().extract(
            _SAMPLE_DOC_TEXT,
            schema=schema,
            document_class="OfficialNotice",
            document_class_id="class-1",
            chunks=chunks,
            config=config,
        )
    assert result.status == "completed"
    assert result.provider == LANGGRAPH_PROVIDER
    assert result.data["Datum"] == "15. März 2021"
    assert result.data["Titel"] == "Habitat Project Alpha"
    assert len(result.data["Auflagen"]) == 2
    assert result.fields["Datum"].evidence
    auflagen_evidence = result.fields["Auflagen"].evidence
    assert auflagen_evidence
    assert all(item.source == "langgraph" for item in auflagen_evidence)
    assert len(result.fields["Auflagen"].item_evidence) == 2
    assert all(result.fields["Auflagen"].item_evidence)
    # One call per field batch: scalars + one object_list.
    assert client.chat.completions.create.call_count == 2
    first_call_kwargs = client.chat.completions.create.call_args_list[0].kwargs
    assert first_call_kwargs["response_format"]["type"] == "json_schema"
    assert first_call_kwargs["response_format"]["json_schema"]["strict"] is True


def test_null_scalar_and_empty_list_normalize_to_missing_values():
    schema = WorkerDocumentExtractionSchema.model_validate(
        {
            "id": "schema-missing",
            "name": "Missing Values",
            "document_class_id": "class-1",
            "document_class": "Missing",
            "fields": [
                {
                    "name": "Datum",
                    "dtype": "date",
                    "description": "Optional date",
                    "required": False,
                },
                {
                    "name": "Tags",
                    "dtype": "list",
                    "description": "Optional tags",
                    "required": False,
                },
            ],
        }
    )
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _fake_openai_response(
            json.dumps(
                {"Datum": {"value": None, "evidence_anchor": None}},
                ensure_ascii=False,
            )
        ),
        _fake_openai_response(json.dumps({"Tags": []}, ensure_ascii=False)),
    ]

    with patch(
        "intextum_worker.services.content_enrichment.langgraph_provider._build_openai_client",
        return_value=client,
    ):
        result = LangGraphExtractionProvider().extract(
            "Document text without those values.",
            schema=schema,
            document_class="Missing",
            document_class_id="class-1",
            chunks=_chunks_for_doc("Document text without those values."),
            config=_config(),
        )

    assert result.status == "completed"
    assert result.fields["Datum"].missing_reason == "not_found"
    assert result.fields["Datum"].value is None
    assert result.fields["Tags"].missing_reason == "not_found"
    assert result.fields["Tags"].value == []
    assert result.data["Tags"] == []


def test_json_schema_unsupported_retries_with_json_object():
    schema = WorkerDocumentExtractionSchema.model_validate(
        {
            "id": "schema-fallback",
            "name": "Fallback Schema",
            "document_class_id": "class-1",
            "document_class": "Fallback",
            "fields": [
                {
                    "name": "Datum",
                    "dtype": "str",
                    "description": "Date",
                    "required": True,
                }
            ],
        }
    )
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        RuntimeError("response_format json_schema is not supported by this backend"),
        _fake_openai_response(
            json.dumps(
                {
                    "Datum": {
                        "value": "15. März 2021",
                        "evidence_anchor": "Datum: 15. März 2021",
                    }
                },
                ensure_ascii=False,
            )
        ),
    ]

    with patch(
        "intextum_worker.services.content_enrichment.langgraph_provider._build_openai_client",
        return_value=client,
    ):
        result = LangGraphExtractionProvider().extract(
            "Datum: 15. März 2021",
            schema=schema,
            document_class="Fallback",
            document_class_id="class-1",
            chunks=_chunks_for_doc("Datum: 15. März 2021"),
            config=_config(),
        )

    assert result.status == "completed"
    assert result.data["Datum"] == "15. März 2021"
    assert (
        client.chat.completions.create.call_args_list[0].kwargs["response_format"][
            "type"
        ]
        == "json_schema"
    )
    assert client.chat.completions.create.call_args_list[1].kwargs[
        "response_format"
    ] == {"type": "json_object"}
    raw_outputs = result.raw_output["raw_llm_outputs"]
    assert raw_outputs[0]["response_format_type"] == "json_schema"
    assert raw_outputs[1]["response_format_fallback"] is True
    assert raw_outputs[1]["fallback_reason"] == "json_schema_unsupported"


def test_missing_required_triggers_one_prompt_only_retry():
    schema = _schema()
    config = _config()
    chunks = _chunks_for_doc(_SAMPLE_DOC_TEXT)

    # Pass 1: scalar batch returns only Titel (Datum missing); object batch
    # returns empty. Pass 2: retry only the scalar batch since that's where
    # the missing required field lives.
    scalar_pass1 = json.dumps(
        {
            "Titel": {
                "value": "Habitat Project Alpha",
                "evidence_anchor": "Titel: Habitat Project Alpha",
            }
        },
        ensure_ascii=False,
    )
    object_pass1 = json.dumps({}, ensure_ascii=False)
    scalar_pass2 = json.dumps(
        {
            "Datum": {
                "value": "15. März 2021",
                "evidence_anchor": "Datum: 15. März 2021",
            }
        },
        ensure_ascii=False,
    )

    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _fake_openai_response(scalar_pass1),
        _fake_openai_response(object_pass1),
        _fake_openai_response(scalar_pass2),
    ]
    with (
        patch(
            "intextum_worker.services.content_enrichment.langgraph_provider._build_openai_client",
            return_value=client,
        ),
        patch(
            "intextum_worker.services.content_enrichment.langgraph_provider._runtime_settings",
            return_value=(1, True, 50_000),
        ),
    ):
        result = LangGraphExtractionProvider().extract(
            _SAMPLE_DOC_TEXT,
            schema=schema,
            document_class="OfficialNotice",
            document_class_id="class-1",
            chunks=chunks,
            config=config,
        )

    assert result.status == "completed"
    # Required field recovered on retry.
    assert result.data["Datum"] == "15. März 2021"
    assert client.chat.completions.create.call_count == 3
    # Retry call should target the scalar batch that holds Datum.
    retry_call_args = client.chat.completions.create.call_args_list[2]
    user_message = retry_call_args.kwargs["messages"][1]["content"]
    assert "Datum" in user_message
    assert "RETRY NOTE" in user_message


def test_semantic_path_used_when_text_exceeds_threshold():
    schema = _schema()
    config = _config()
    long_text = ("A" * 30) + "\n" + _SAMPLE_DOC_TEXT * 10
    chunks = _chunks_for_doc(_SAMPLE_DOC_TEXT)
    llm_payload = {
        "Datum": {
            "value": "15. März 2021",
            "evidence_anchor": "Datum: 15. März 2021",
        }
    }
    client = MagicMock()
    client.chat.completions.create.return_value = _fake_openai_response(
        json.dumps(llm_payload, ensure_ascii=False)
    )
    select_called = {"value": False}

    def _fake_select(*args, **kwargs):
        select_called["value"] = True
        return chunks, 4, None

    with (
        patch(
            "intextum_worker.services.content_enrichment.langgraph_provider._build_openai_client",
            return_value=client,
        ),
        patch(
            "intextum_worker.services.content_enrichment.langgraph_provider._select_extraction_chunks",
            side_effect=_fake_select,
        ),
        patch(
            "intextum_worker.services.content_enrichment.langgraph_provider._runtime_settings",
            return_value=(0, False, 200),  # threshold below text length forces semantic
        ),
    ):
        result = LangGraphExtractionProvider().extract(
            long_text,
            schema=schema,
            document_class="OfficialNotice",
            document_class_id="class-1",
            chunks=chunks,
            config=config,
        )
    assert select_called["value"] is True
    assert result.status == "completed"
    assert result.data["Datum"] == "15. März 2021"
    # Evidence still present despite chunk concatenation with "[Chunk N]" markers.
    assert result.fields["Datum"].evidence


def test_missing_evidence_flagged_when_required():
    schema = _schema()
    config = _config()
    chunks = _chunks_for_doc(_SAMPLE_DOC_TEXT)
    llm_payload = {
        "Datum": {
            "value": "15.3.2021",  # value present but quote is paraphrased
            "evidence_anchor": "March 15, 2021",  # not in source
        },
        "Titel": {
            "value": "Habitat Project Alpha",
            "evidence_anchor": "Titel: Habitat Project Alpha",
        },
    }
    client = MagicMock()
    client.chat.completions.create.return_value = _fake_openai_response(
        json.dumps(llm_payload, ensure_ascii=False)
    )
    with (
        patch(
            "intextum_worker.services.content_enrichment.langgraph_provider._build_openai_client",
            return_value=client,
        ),
        patch(
            "intextum_worker.services.content_enrichment.langgraph_provider._runtime_settings",
            return_value=(0, True, 50_000),
        ),
    ):
        result = LangGraphExtractionProvider().extract(
            _SAMPLE_DOC_TEXT,
            schema=schema,
            document_class="OfficialNotice",
            document_class_id="class-1",
            chunks=chunks,
            config=config,
        )
    assert "Datum" in (result.summary.fields_without_evidence or [])
    assert "Titel" not in (result.summary.fields_without_evidence or [])
    assert "evidence_anchor_not_found" in result.fields["Datum"].validation_errors


def test_list_fields_run_separately_with_focused_source_window():
    schema = WorkerDocumentExtractionSchema.model_validate(
        {
            "id": "schema-1",
            "name": "OfficialNotice",
            "document_class_id": "class-1",
            "document_class": "OfficialNotice",
            "fields": [
                {
                    "name": "Datum",
                    "dtype": "str",
                    "description": "Date of letter",
                    "required": False,
                    "extraction_mode": "chat",
                },
                {
                    "name": "Nebenbestimmungen",
                    "dtype": "list",
                    "description": "Extrahiere alle Nebenbestimmungen",
                    "required": False,
                    "extraction_mode": "chat",
                },
            ],
        }
    )
    chunks = [
        SimpleNamespace(chunk_index=0, text="Datum: 15. März 2021", page_numbers=[1]),
        SimpleNamespace(
            chunk_index=1,
            text="Die unter I. genannte Approval ergeht unter folgenden Nebenbestimmungen:",
            page_numbers=[1],
        ),
        SimpleNamespace(
            chunk_index=2,
            text=(
                "1. Erste Auflage muss erfüllt werden.\n"
                "2. Zweite Auflage betrifft Monitoring."
            ),
            page_numbers=[1],
        ),
        SimpleNamespace(
            chunk_index=3,
            text="Begründung: Diese lange Passage ist nicht Teil der Nebenbestimmungen.",
            page_numbers=[2],
        ),
    ]
    text = "\n\n".join(chunk.text for chunk in chunks)
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _fake_openai_response(
            json.dumps(
                {
                    "Datum": {
                        "value": "15. März 2021",
                        "evidence_anchor": "Datum: 15. März 2021",
                    }
                },
                ensure_ascii=False,
            )
        ),
        _fake_openai_response(
            json.dumps(
                {
                    "Nebenbestimmungen": [
                        "1. Erste Auflage muss erfüllt werden.",
                        "2. Zweite Auflage betrifft Monitoring.",
                    ]
                },
                ensure_ascii=False,
            )
        ),
    ]

    with patch(
        "intextum_worker.services.content_enrichment.langgraph_provider._build_openai_client",
        return_value=client,
    ):
        result = LangGraphExtractionProvider().extract(
            text,
            schema=schema,
            document_class="OfficialNotice",
            document_class_id="class-1",
            chunks=chunks,
            config=_config(),
        )

    assert result.status == "completed"
    assert client.chat.completions.create.call_count == 2
    scalar_prompt = client.chat.completions.create.call_args_list[0].kwargs["messages"][
        1
    ]["content"]
    list_prompt = client.chat.completions.create.call_args_list[1].kwargs["messages"][
        1
    ]["content"]
    assert "FIELDS TO EXTRACT: Datum" in scalar_prompt
    assert "FIELDS TO EXTRACT: Nebenbestimmungen" in list_prompt
    assert '"Nebenbestimmungen": [ "<one verbatim list item>", ... ]' in list_prompt
    assert "Do not wrap list items in objects" in list_prompt
    assert "1. Erste Auflage muss erfüllt werden." in list_prompt
    assert "Begründung: Diese lange Passage" not in list_prompt
    assert result.data["Nebenbestimmungen"] == [
        "1. Erste Auflage muss erfüllt werden.",
        "2. Zweite Auflage betrifft Monitoring.",
    ]


def test_list_field_focus_prefers_section_heading_over_generic_reference():
    schema = WorkerDocumentExtractionSchema.model_validate(
        {
            "id": "schema-1",
            "name": "OfficialNotice",
            "document_class_id": "class-1",
            "document_class": "OfficialNotice",
            "fields": [
                {
                    "name": "Nebenbestimmungen",
                    "dtype": "list",
                    "description": "Extrahiere alle Nebenbestimmungen",
                    "required": False,
                    "extraction_mode": "chat",
                },
            ],
        }
    )
    chunks = [
        SimpleNamespace(
            chunk_index=3,
            text=(
                "Gemäß § 16 BNatSchG wird die Planung unter Beachtung der "
                "Conditions approved:"
            ),
            page_numbers=[1],
        ),
        SimpleNamespace(
            chunk_index=4,
            text=(
                "Der Approval liegen folgende Unterlagen zugrunde.\n"
                "Die unter I. genannte Approval ergeht unter folgenden "
                "Nebenbestimmungen:"
            ),
            page_numbers=[1, 2],
        ),
        SimpleNamespace(
            chunk_index=5,
            text=(
                "1. Die CompensationMeasure ist gemäß den planning documents "
                "auszuführen.\n"
                "2. Der Maßnahmenbeginn ist der authority anzuzeigen."
            ),
            page_numbers=[2],
        ),
        SimpleNamespace(
            chunk_index=6,
            text="Begründung: Diese Passage ist nicht Teil der Nebenbestimmungen.",
            page_numbers=[3],
        ),
    ]
    text = "\n\n".join(chunk.text for chunk in chunks)
    client = MagicMock()
    client.chat.completions.create.return_value = _fake_openai_response(
        json.dumps(
            {
                "Nebenbestimmungen": [
                    "1. Die CompensationMeasure ist gemäß den planning documents auszuführen.",
                    "2. Der Maßnahmenbeginn ist der authority anzuzeigen.",
                ]
            },
            ensure_ascii=False,
        )
    )

    with patch(
        "intextum_worker.services.content_enrichment.langgraph_provider._build_openai_client",
        return_value=client,
    ):
        result = LangGraphExtractionProvider().extract(
            text,
            schema=schema,
            document_class="OfficialNotice",
            document_class_id="class-1",
            chunks=chunks,
            config=_config(),
        )

    assert result.status == "completed"
    list_prompt = client.chat.completions.create.call_args.kwargs["messages"][1][
        "content"
    ]
    assert "unter folgenden Nebenbestimmungen" in list_prompt
    assert "1. Die CompensationMeasure" in list_prompt
    assert "Begründung: Diese Passage" not in list_prompt
    assert result.data["Nebenbestimmungen"] == [
        "1. Die CompensationMeasure ist gemäß den planning documents auszuführen.",
        "2. Der Maßnahmenbeginn ist der authority anzuzeigen.",
    ]


def test_items_without_evidence_counts_each_missing_record():
    """All-missing-evidence records should be counted, not collapsed to one token."""
    schema = WorkerDocumentExtractionSchema.model_validate(
        {
            "id": "schema-list",
            "name": "ListSchema",
            "document_class_id": "class-list",
            "document_class": "ListClass",
            "fields": [
                {
                    "name": "items",
                    "dtype": "list",
                    "description": "Three items, all without verifiable anchors",
                    "required": False,
                    "extraction_mode": "chat",
                    "clustered_under_heading": False,
                },
            ],
        }
    )
    chunks = _chunks_for_doc("Body text without anchor matches.")
    payload = json.dumps(
        {
            "items": [
                {"value": "alpha", "evidence_anchor": "no-such-anchor-1"},
                {"value": "beta", "evidence_anchor": "no-such-anchor-2"},
                {"value": "gamma", "evidence_anchor": "no-such-anchor-3"},
            ]
        },
        ensure_ascii=False,
    )
    client = MagicMock()
    client.chat.completions.create.return_value = _fake_openai_response(payload)
    with patch(
        "intextum_worker.services.content_enrichment.langgraph_provider._build_openai_client",
        return_value=client,
    ):
        result = LangGraphExtractionProvider().extract(
            "Body text without anchor matches.",
            schema=schema,
            document_class="ListClass",
            document_class_id="class-list",
            chunks=chunks,
            config=_config(),
        )
    assert result.status == "completed"
    items_field = result.fields["items"]
    assert items_field.items_without_evidence == 3
    assert "evidence_anchor_not_found" in items_field.validation_errors


def test_scattered_list_field_skips_focused_window():
    """clustered_under_heading=False keeps the full prompt for scattered lists."""
    schema = WorkerDocumentExtractionSchema.model_validate(
        {
            "id": "schema-emails",
            "name": "EmailMentions",
            "document_class_id": "class-emails",
            "document_class": "Correspondence",
            "fields": [
                {
                    "name": "email_addresses",
                    "dtype": "list",
                    "description": "All email addresses mentioned anywhere",
                    "required": False,
                    "extraction_mode": "chat",
                    "clustered_under_heading": False,
                },
            ],
        }
    )
    chunks = [
        SimpleNamespace(
            chunk_index=0,
            text="Email addresses: please contact a@example.com for details.",
            page_numbers=[1],
        ),
        SimpleNamespace(
            chunk_index=1,
            text="Unrelated middle paragraph with no contact info.",
            page_numbers=[1],
        ),
        SimpleNamespace(
            chunk_index=2,
            text="Footer: legal@example.com and press@example.com are reachable.",
            page_numbers=[2],
        ),
    ]
    text = "\n\n".join(chunk.text for chunk in chunks)
    client = MagicMock()
    client.chat.completions.create.return_value = _fake_openai_response(
        json.dumps(
            {
                "email_addresses": [
                    "a@example.com",
                    "legal@example.com",
                    "press@example.com",
                ]
            },
            ensure_ascii=False,
        )
    )
    with patch(
        "intextum_worker.services.content_enrichment.langgraph_provider._build_openai_client",
        return_value=client,
    ):
        result = LangGraphExtractionProvider().extract(
            text,
            schema=schema,
            document_class="Correspondence",
            document_class_id="class-emails",
            chunks=chunks,
            config=_config(),
        )

    assert result.status == "completed"
    list_prompt = client.chat.completions.create.call_args.kwargs["messages"][1][
        "content"
    ]
    # All three chunks must be present — focused-window narrowing was skipped.
    assert "a@example.com" in list_prompt
    assert "Unrelated middle paragraph" in list_prompt
    assert "legal@example.com" in list_prompt


def test_heading_aliases_match_german_section_for_english_named_field():
    """English-named field with German alias should still find the German section."""
    schema = WorkerDocumentExtractionSchema.model_validate(
        {
            "id": "schema-aux",
            "name": "Permit",
            "document_class_id": "class-permit",
            "document_class": "Permit",
            "fields": [
                {
                    "name": "ancillary_conditions",
                    "dtype": "list",
                    "description": "Extracted ancillary conditions",
                    "required": False,
                    "extraction_mode": "chat",
                    "heading_aliases": ["Nebenbestimmungen"],
                },
            ],
            "section_boundary_terms": ["Begründung", "Rechtsbehelf"],
        }
    )
    chunks = [
        SimpleNamespace(
            chunk_index=0,
            text=(
                "Die unter I. genannte Approval ergeht unter folgenden "
                "Nebenbestimmungen:"
            ),
            page_numbers=[1],
        ),
        SimpleNamespace(
            chunk_index=1,
            text="1. Erste Auflage.\n2. Zweite Auflage.",
            page_numbers=[1],
        ),
        SimpleNamespace(
            chunk_index=2,
            text="Begründung: Diese Passage gehört nicht in die Liste.",
            page_numbers=[2],
        ),
    ]
    text = "\n\n".join(chunk.text for chunk in chunks)
    client = MagicMock()
    client.chat.completions.create.return_value = _fake_openai_response(
        json.dumps(
            {"ancillary_conditions": ["1. Erste Auflage.", "2. Zweite Auflage."]},
            ensure_ascii=False,
        )
    )
    with patch(
        "intextum_worker.services.content_enrichment.langgraph_provider._build_openai_client",
        return_value=client,
    ):
        result = LangGraphExtractionProvider().extract(
            text,
            schema=schema,
            document_class="Permit",
            document_class_id="class-permit",
            chunks=chunks,
            config=_config(),
        )

    assert result.status == "completed"
    list_prompt = client.chat.completions.create.call_args.kwargs["messages"][1][
        "content"
    ]
    # Heading match drove the focused window: the German list chunks made it in,
    # the Begründung boundary chunk did not.
    assert "folgenden Nebenbestimmungen" in list_prompt
    assert "Erste Auflage" in list_prompt
    assert "Begründung" not in list_prompt
    assert result.data["ancillary_conditions"] == [
        "1. Erste Auflage.",
        "2. Zweite Auflage.",
    ]


def test_focused_repeated_field_chunks_stop_at_declared_boundary():
    """Schema boundary terms should end a repeated-field evidence window."""
    schema = WorkerDocumentExtractionSchema.model_validate(
        {
            "id": "schema-conditions",
            "name": "Permit",
            "document_class_id": "class-permit",
            "document_class": "Permit",
            "fields": [
                {
                    "name": "ancillary_conditions",
                    "dtype": "list",
                    "description": "Extract conditions",
                    "required": False,
                    "extraction_mode": "chat",
                    "heading_aliases": ["Nebenbestimmungen"],
                },
            ],
            "section_boundary_terms": ["Rechtsbehelf"],
        }
    )
    chunks = [
        SimpleNamespace(
            chunk_index=0,
            text="Die Approval ergeht unter folgenden Nebenbestimmungen:",
        ),
        SimpleNamespace(chunk_index=1, text="1. Erste Auflage."),
        SimpleNamespace(chunk_index=2, text="Rechtsbehelf: Klage binnen eines Monats."),
    ]

    focused = _focused_repeated_field_chunks(
        chunks=chunks,
        field=schema.fields[0],
        boundary_terms=("rechtsbehelf",),
    )

    assert [chunk.chunk_index for chunk in focused] == [0, 1]


def test_focused_repeated_field_chunks_keep_numbered_continuations_only():
    """After the first body chunk, only list-like continuations extend the window."""
    schema = WorkerDocumentExtractionSchema.model_validate(
        {
            "id": "schema-conditions",
            "name": "Permit",
            "document_class_id": "class-permit",
            "document_class": "Permit",
            "fields": [
                {
                    "name": "Nebenbestimmungen",
                    "dtype": "list",
                    "description": "Extract conditions",
                    "required": False,
                    "extraction_mode": "chat",
                },
            ],
        }
    )
    chunks = [
        SimpleNamespace(
            chunk_index=0,
            text="Die Approval ergeht unter folgenden Nebenbestimmungen:",
        ),
        SimpleNamespace(chunk_index=1, text="1. Erste Auflage."),
        SimpleNamespace(chunk_index=2, text="2. Zweite Auflage."),
        SimpleNamespace(chunk_index=3, text="Diese spätere Passage gehört nicht dazu."),
    ]

    focused = _focused_repeated_field_chunks(
        chunks=chunks,
        field=schema.fields[0],
        boundary_terms=(),
    )

    assert [chunk.chunk_index for chunk in focused] == [0, 1, 2]


def test_invalid_json_batch_fails_even_after_other_fields_parse():
    schema = _schema()
    config = _config()
    chunks = _chunks_for_doc(_SAMPLE_DOC_TEXT)
    # Scalar batch parses cleanly.
    scalar_payload = json.dumps(
        {
            "Datum": {
                "value": "15. März 2021",
                "evidence_anchor": "Datum: 15. März 2021",
            },
            "Titel": {
                "value": "Habitat Project Alpha",
                "evidence_anchor": "Titel: Habitat Project Alpha",
            },
        },
        ensure_ascii=False,
    )
    # Object batch payload is two intact records plus a third truncated mid-string.
    truncated_object_payload = (
        '{"Auflagen": ['
        '{"value": {"Nummer": "1", "Text": "Erste Auflage muss erfüllt werden."},'
        ' "evidence_anchor": "1. Erste Auflage"},'
        '{"value": {"Nummer": "2", "Text": "Zweite Auflage betrifft Monitoring."},'
        ' "evidence_anchor": "2. Zweite Auflage"},'
        '{"value": {"Nummer": "3", "Text": "Dritte unfertige Au'
    )
    client = MagicMock()

    def _responses():
        yield _fake_openai_response(scalar_payload)
        while True:
            yield _fake_openai_response(
                truncated_object_payload, finish_reason="length"
            )

    response_iter = _responses()
    client.chat.completions.create.side_effect = lambda *_, **__: next(response_iter)
    with (
        patch(
            "intextum_worker.services.content_enrichment.langgraph_provider._build_openai_client",
            return_value=client,
        ),
        patch(
            "intextum_worker.services.content_enrichment.langgraph_provider._runtime_settings",
            return_value=(0, True, 50_000),
        ),
    ):
        result = LangGraphExtractionProvider().extract(
            _SAMPLE_DOC_TEXT,
            schema=schema,
            document_class="OfficialNotice",
            document_class_id="class-1",
            chunks=chunks,
            config=config,
        )
    assert result.status == "failed"
    assert result.error and "chat_invalid_json" in result.error
    assert all(
        call.kwargs["response_format"]["type"] == "json_schema"
        for call in client.chat.completions.create.call_args_list
    )


def test_length_finish_retries_with_larger_token_budget():
    schema = _schema()
    config = _config()
    chunks = _chunks_for_doc(_SAMPLE_DOC_TEXT)
    scalar_payload = json.dumps(
        {
            "Datum": {
                "value": "15. März 2021",
                "evidence_anchor": "Datum: 15. März 2021",
            },
            "Titel": {
                "value": "Habitat Project Alpha",
                "evidence_anchor": "Titel: Habitat Project Alpha",
            },
        },
        ensure_ascii=False,
    )
    truncated_payload = '{"Auflagen": ['
    full_payload = json.dumps(
        {
            "Auflagen": [
                {
                    "value": {"Nummer": "1", "Text": "Erste"},
                    "evidence_anchor": "1. Erste Auflage",
                },
            ]
        },
        ensure_ascii=False,
    )
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _fake_openai_response(scalar_payload),
        _fake_openai_response(truncated_payload, finish_reason="length"),
        _fake_openai_response(full_payload),
    ]
    with (
        patch(
            "intextum_worker.services.content_enrichment.langgraph_provider._build_openai_client",
            return_value=client,
        ),
        patch(
            "intextum_worker.services.content_enrichment.langgraph_provider._runtime_settings",
            return_value=(0, True, 50_000),
        ),
    ):
        result = LangGraphExtractionProvider().extract(
            _SAMPLE_DOC_TEXT,
            schema=schema,
            document_class="OfficialNotice",
            document_class_id="class-1",
            chunks=chunks,
            config=config,
        )
    assert result.status == "completed"
    assert result.data["Auflagen"] == [{"Nummer": "1", "Text": "Erste"}]
    # 1 scalar call + 2 object-batch calls (initial length + retry that succeeded).
    assert client.chat.completions.create.call_count == 3
    retry_call_kwargs = client.chat.completions.create.call_args_list[2].kwargs
    assert retry_call_kwargs["max_tokens"] == config.max_output_tokens * 2
    assert retry_call_kwargs["response_format"]["type"] == "json_schema"


def test_fuzzy_locate_recovers_whitespace_variants():
    text = "Line one.\n\n  Line two\twith\nspaces."
    assert _fuzzy_locate("Line two with spaces.", text) >= 0


def test_invalid_json_marks_extraction_failed():
    schema = _schema()
    config = _config()
    chunks = _chunks_for_doc(_SAMPLE_DOC_TEXT)
    client = MagicMock()
    client.chat.completions.create.return_value = _fake_openai_response(
        "not json at all"
    )
    with (
        patch(
            "intextum_worker.services.content_enrichment.langgraph_provider._build_openai_client",
            return_value=client,
        ),
        patch(
            "intextum_worker.services.content_enrichment.langgraph_provider._runtime_settings",
            return_value=(0, True, 50_000),
        ),
    ):
        result = LangGraphExtractionProvider().extract(
            _SAMPLE_DOC_TEXT,
            schema=schema,
            document_class="OfficialNotice",
            document_class_id="class-1",
            chunks=chunks,
            config=config,
        )
    assert result.status == "failed"
    assert result.error and "chat_invalid_json" in result.error


def test_empty_chat_content_marks_extraction_failed():
    schema = _schema()
    config = _config()
    chunks = _chunks_for_doc(_SAMPLE_DOC_TEXT)
    client = MagicMock()
    client.chat.completions.create.return_value = _fake_openai_response("")
    with (
        patch(
            "intextum_worker.services.content_enrichment.langgraph_provider._build_openai_client",
            return_value=client,
        ),
        patch(
            "intextum_worker.services.content_enrichment.langgraph_provider._runtime_settings",
            return_value=(0, True, 50_000),
        ),
    ):
        result = LangGraphExtractionProvider().extract(
            _SAMPLE_DOC_TEXT,
            schema=schema,
            document_class="OfficialNotice",
            document_class_id="class-1",
            chunks=chunks,
            config=config,
        )
    assert result.status == "failed"
    assert result.error and "chat_invalid_json" in result.error
    assert "empty assistant content" in result.error
