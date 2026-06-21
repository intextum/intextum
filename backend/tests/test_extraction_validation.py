"""Focused tests for provider-agnostic extraction payload validation."""

from models.ai_settings import EffectiveAiSettings
from services.content.enrichment.extraction_validation import (
    validate_extraction_payload,
)


def _settings() -> EffectiveAiSettings:
    return EffectiveAiSettings.model_validate(
        {
            "chat_model": "test-chat-model",
            "chat_system_prompt": "You are a helpful assistant.",
            "chat_tool_prompt": "Use the available tools when needed.",
            "chat_search_limit": 10,
            "chat_document_max_chars": 30000,
            "picture_description_model": "test-picture-model",
            "picture_description_prompt": "Describe the image accurately.",
            "document_classification_enabled": True,
            "document_classification_model": "fastino/gliner2-multi-v1",
            "document_classification_labels": [
                {
                    "name": "Invoice",
                    "description": "Invoice documents",
                    "aliases": [],
                }
            ],
            "document_extraction_enabled": True,
            "document_extraction_model": "fastino/gliner2-multi-v1",
            "document_extraction_schemas": [
                {
                    "name": "invoice_fields",
                    "document_class": "Invoice",
                    "description": "Invoice fields",
                    "fields": [
                        {
                            "name": "invoice_number",
                            "dtype": "str",
                            "description": "Invoice number",
                            "required": True,
                        },
                        {
                            "name": "gross_amount",
                            "dtype": "currency",
                            "description": "Gross invoice amount",
                        },
                        {
                            "name": "invoice_date",
                            "dtype": "date",
                            "description": "Invoice date",
                        },
                        {
                            "name": "paid",
                            "dtype": "bool",
                            "description": "Payment status",
                        },
                        {
                            "name": "line_items",
                            "dtype": "object_list",
                            "description": "Invoice line items",
                            "fields": [
                                {
                                    "name": "description",
                                    "dtype": "str",
                                    "description": "Line description",
                                    "required": True,
                                },
                                {
                                    "name": "quantity",
                                    "dtype": "int",
                                    "description": "Line quantity",
                                    "required": True,
                                },
                            ],
                        },
                    ],
                }
            ],
            "document_extraction_max_chars": 12000,
        }
    )


def test_validate_extraction_payload_coerces_scalars_and_nested_fields():
    payload = {
        "status": "completed",
        "provider": "worker",
        "model": "extractor",
        "fields": {
            "invoice_number": {
                "value": " RE-2026-42 ",
                "evidence": ["Invoice RE-2026-42"],
            },
            "gross_amount": {
                "value": "1.234,56 EUR",
                "evidence": ["Total 1.234,56 EUR"],
            },
            "invoice_date": {
                "value": "02.05.2026",
                "evidence": ["Date 02.05.2026"],
            },
            "paid": {"value": "ja", "evidence": ["Paid: ja"]},
            "line_items": {
                "value": [
                    {"description": " Consulting ", "quantity": "2"},
                    {"description": "", "quantity": "3,5"},
                ],
                "item_evidence": [["Consulting x2"], ["Broken quantity"]],
            },
        },
    }

    result = validate_extraction_payload(
        payload,
        settings=_settings(),
        class_id=None,
        class_label="Invoice",
    )

    assert result.trusted is True
    assert result.status == "completed"
    assert result.data["invoice_number"] == "RE-2026-42"
    assert result.data["gross_amount"] == {"amount": 1234.56, "currency": "EUR"}
    assert result.data["invoice_date"] == "2026-05-02"
    assert result.data["paid"] is True
    assert result.data["line_items"] == [{"description": "Consulting", "quantity": 2}]
    assert result.fields["line_items"]["validation_errors"] == [
        "line_items[1].quantity"
    ]
    assert result.summary["missing_required_fields"] == ["line_items[1].description"]
    assert result.summary["invalid_fields"] == ["line_items[1].quantity"]
    assert result.summary["fields_without_evidence"] == []
    assert result.summary["needs_review"] is True
