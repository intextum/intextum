"""Tests for content enrichment catalog admin routes."""

from unittest.mock import AsyncMock, patch

from auth.dependencies import require_admin
from models.content.enrichment_catalog import ContentEnrichmentCatalogResponse
from models.user import User


def _admin_user() -> User:
    return User(username="admin", sub="sub-admin", groups=["admins"])


def _catalog_response() -> ContentEnrichmentCatalogResponse:
    return ContentEnrichmentCatalogResponse(
        document_classes=[
            {
                "name": "Invoice",
                "version": 2,
                "description": "Billing document",
                "aliases": ["Rechnung"],
                "extraction_schema": {
                    "name": "invoice_fields",
                    "version": 3,
                    "description": "Extract invoice fields",
                    "fields": [
                        {
                            "name": "invoice_number",
                            "dtype": "str",
                            "description": "Invoice number",
                            "required": True,
                        }
                    ],
                },
            }
        ],
    )


def test_get_content_enrichment_catalog_returns_class_owned_payload(test_client):
    from main import app

    app.dependency_overrides[require_admin] = _admin_user
    try:
        with patch(
            "routers.admin.content_enrichment_catalog.ContentEnrichmentCatalogService.get_catalog",
            new=AsyncMock(return_value=_catalog_response()),
        ):
            response = test_client.get("/api/content-enrichment-catalog")
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    payload = response.json()
    assert list(payload) == ["document_classes"]
    assert payload["document_classes"][0]["name"] == "Invoice"
    assert payload["document_classes"][0]["version"] == 2
    assert (
        payload["document_classes"][0]["extraction_schema"]["name"] == "invoice_fields"
    )
    assert payload["document_classes"][0]["extraction_schema"]["version"] == 3


def test_put_content_enrichment_catalog_replaces_class_owned_payload(test_client):
    from main import app

    request_payload = {
        "document_classes": [
            {
                "name": "Invoice",
                "description": "Billing document",
                "aliases": ["Rechnung"],
                "extraction_schema": {
                    "name": "invoice_fields",
                    "description": "Extract invoice fields",
                    "fields": [
                        {
                            "name": "invoice_number",
                            "dtype": "str",
                            "description": "Invoice number",
                            "required": True,
                        }
                    ],
                },
            }
        ],
    }

    app.dependency_overrides[require_admin] = _admin_user
    try:
        with patch(
            "routers.admin.content_enrichment_catalog.ContentEnrichmentCatalogService.replace_catalog",
            new=AsyncMock(return_value=_catalog_response()),
        ) as replace_catalog:
            response = test_client.put(
                "/api/content-enrichment-catalog",
                json=request_payload,
            )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    assert replace_catalog.await_count == 1
    document_classes = replace_catalog.await_args.kwargs["document_classes"]
    assert len(document_classes) == 1
    assert document_classes[0].name == "Invoice"
    assert document_classes[0].extraction_schema.name == "invoice_fields"


def test_put_content_enrichment_catalog_allows_object_list_without_examples(
    test_client,
):
    from main import app

    request_payload = {
        "document_classes": [
            {
                "name": "Permit",
                "description": "",
                "aliases": [],
                "extraction_schema": {
                    "name": "permit_fields",
                    "description": "",
                    "fields": [
                        {
                            "name": "tasks",
                            "dtype": "object_list",
                            "description": "Tasks",
                            "fields": [
                                {
                                    "name": "title",
                                    "dtype": "str",
                                    "description": "Task title",
                                }
                            ],
                            "examples": [],
                        }
                    ],
                },
            }
        ],
    }

    app.dependency_overrides[require_admin] = _admin_user
    try:
        with patch(
            "routers.admin.content_enrichment_catalog.ContentEnrichmentCatalogService.replace_catalog",
            new=AsyncMock(return_value=_catalog_response()),
        ) as replace_catalog:
            response = test_client.put(
                "/api/content-enrichment-catalog",
                json=request_payload,
            )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    assert replace_catalog.await_count == 1


def test_put_content_enrichment_catalog_allows_scalar_without_examples(
    test_client,
):
    from main import app

    request_payload = {
        "document_classes": [
            {
                "name": "Permit",
                "description": "",
                "aliases": [],
                "extraction_schema": {
                    "name": "permit_fields",
                    "description": "",
                    "fields": [
                        {
                            "name": "due_date",
                            "dtype": "date",
                            "description": "Global due date",
                            "examples": [],
                        }
                    ],
                },
            }
        ],
    }

    app.dependency_overrides[require_admin] = _admin_user
    try:
        with patch(
            "routers.admin.content_enrichment_catalog.ContentEnrichmentCatalogService.replace_catalog",
            new=AsyncMock(return_value=_catalog_response()),
        ) as replace_catalog:
            response = test_client.put(
                "/api/content-enrichment-catalog",
                json=request_payload,
            )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    assert replace_catalog.await_count == 1


def test_put_content_enrichment_catalog_rejects_object_list_without_fields(
    test_client,
):
    from main import app

    request_payload = {
        "document_classes": [
            {
                "name": "Permit",
                "description": "",
                "aliases": [],
                "extraction_schema": {
                    "name": "permit_fields",
                    "description": "",
                    "fields": [
                        {
                            "name": "tasks",
                            "dtype": "object_list",
                            "description": "Tasks",
                            "fields": [],
                            "examples": [],
                        }
                    ],
                },
            }
        ],
    }

    app.dependency_overrides[require_admin] = _admin_user
    try:
        response = test_client.put(
            "/api/content-enrichment-catalog",
            json=request_payload,
        )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 422
    assert "object_list_fields_required" in response.text


def test_reset_content_enrichment_catalog_resets_to_defaults(test_client):
    from main import app

    app.dependency_overrides[require_admin] = _admin_user
    try:
        with patch(
            "routers.admin.content_enrichment_catalog.ContentEnrichmentCatalogService.reset_catalog",
            new=AsyncMock(return_value=_catalog_response()),
        ) as reset_catalog:
            response = test_client.post("/api/content-enrichment-catalog/reset")
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    assert reset_catalog.await_count == 1


def test_put_content_enrichment_catalog_returns_bad_request_for_duplicate_definitions(
    test_client,
):
    from main import app

    app.dependency_overrides[require_admin] = _admin_user
    try:
        with patch(
            "routers.admin.content_enrichment_catalog.ContentEnrichmentCatalogService.replace_catalog",
            new=AsyncMock(side_effect=ValueError("Duplicate document class name")),
        ):
            response = test_client.put(
                "/api/content-enrichment-catalog",
                json={
                    "document_classes": [
                        {"name": "Invoice", "description": "", "aliases": []}
                    ],
                },
            )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 400
    assert response.json()["detail"] == "Duplicate document class name"


def test_publish_content_enrichment_catalog_endpoint_is_removed(test_client):
    from main import app

    app.dependency_overrides[require_admin] = _admin_user
    try:
        response = test_client.post("/api/content-enrichment-catalog/publish")
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 404


def test_suggest_field_example_candidates_returns_candidates(test_client):
    from main import app
    from models.content.enrichment_catalog import (
        ContentEnrichmentFieldExampleCandidate,
        ContentEnrichmentFieldExampleCandidatesResponse,
    )

    candidates = ContentEnrichmentFieldExampleCandidatesResponse(
        candidates=[
            ContentEnrichmentFieldExampleCandidate(
                content_item_id="file-1",
                relative_path="docs/invoice.pdf",
                review_status="accepted",
                text="Invoice No. 4711 issued on 2026-05-15.",
                anchor_text="4711",
                value="4711",
                page_numbers=[1],
                chunk_index=2,
            )
        ]
    )

    app.dependency_overrides[require_admin] = _admin_user
    try:
        with patch(
            "routers.admin.content_enrichment_catalog.ContentEnrichmentFieldExampleService.suggest_candidates",
            new=AsyncMock(return_value=candidates),
        ):
            response = test_client.post(
                "/api/content-enrichment-catalog/schemas/invoice_fields/fields/invoice_number/example-candidates",
                json={"content_item_ids": ["file-1"]},
            )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    body = response.json()
    assert len(body["candidates"]) == 1
    assert body["candidates"][0]["anchor_text"] == "4711"
    assert body["candidates"][0]["value"] == "4711"


def test_suggest_field_example_candidates_returns_404_for_unknown_schema(test_client):
    from main import app
    from services.content.enrichment import UnknownSchemaError

    app.dependency_overrides[require_admin] = _admin_user
    try:
        with patch(
            "routers.admin.content_enrichment_catalog.ContentEnrichmentFieldExampleService.suggest_candidates",
            new=AsyncMock(side_effect=UnknownSchemaError("missing_schema")),
        ):
            response = test_client.post(
                "/api/content-enrichment-catalog/schemas/missing_schema/fields/x/example-candidates",
                json={"content_item_ids": []},
            )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown extraction schema"


def test_suggest_field_example_candidates_returns_404_for_unknown_field(test_client):
    from main import app
    from services.content.enrichment import UnknownFieldError

    app.dependency_overrides[require_admin] = _admin_user
    try:
        with patch(
            "routers.admin.content_enrichment_catalog.ContentEnrichmentFieldExampleService.suggest_candidates",
            new=AsyncMock(side_effect=UnknownFieldError("missing_field")),
        ):
            response = test_client.post(
                "/api/content-enrichment-catalog/schemas/invoice_fields/fields/missing_field/example-candidates",
                json={"content_item_ids": []},
            )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown extraction field"
