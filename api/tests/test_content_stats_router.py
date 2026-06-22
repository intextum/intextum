"""Tests for file stats router behavior."""

from unittest.mock import AsyncMock, patch

from auth.dependencies import require_user
from models.content.items import FlatContentItemListResponse
from models.user import User


def test_stats_endpoint_passes_user_to_service(test_client):
    """The stats endpoint should pass current user to service-level ACL filtering."""
    from main import app

    user = User(username="alice", groups=["users"])
    app.dependency_overrides[require_user] = lambda: user
    try:
        with patch(
            "services.content.stats.ContentStatsService.get_global_stats",
            new=AsyncMock(
                return_value={
                    "total_items": 1,
                    "total_size_bytes": 2,
                    "processing_count": 0,
                    "stale_enrichment_count": 0,
                }
            ),
        ) as mock_get_stats:
            response = test_client.get("/api/content/stats")
    finally:
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 200
    assert response.json() == {
        "total_items": 1,
        "total_size_bytes": 2,
        "processing_count": 0,
        "stale_enrichment_count": 0,
    }
    assert mock_get_stats.await_count == 1
    assert mock_get_stats.await_args.args[0] is user


def test_all_files_endpoint_passes_document_class_filter_to_service(test_client):
    """The content-list endpoint should forward the document class filter."""
    from main import app

    user = User(username="alice", groups=["users"])
    app.dependency_overrides[require_user] = lambda: user
    try:
        with patch(
            "services.content.stats.ContentStatsService.list_all_files",
            new=AsyncMock(
                return_value=FlatContentItemListResponse(
                    files=[],
                    total=0,
                    limit=50,
                    offset=0,
                    has_more=False,
                )
            ),
        ) as mock_list_all:
            response = test_client.get("/api/content/all?document_class=invoice")
    finally:
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 200
    assert mock_list_all.await_count == 1
    assert mock_list_all.await_args.kwargs["user"] is user
    assert mock_list_all.await_args.kwargs["document_class"] == "invoice"


def test_all_files_endpoint_passes_ids_filter_to_service(test_client):
    """Repeated ``ids`` query params forward to the service as an ordered tuple."""
    from main import app

    user = User(username="alice", groups=["users"])
    app.dependency_overrides[require_user] = lambda: user
    try:
        with patch(
            "services.content.stats.ContentStatsService.list_all_files",
            new=AsyncMock(
                return_value=FlatContentItemListResponse(
                    files=[],
                    total=0,
                    limit=50,
                    offset=0,
                    has_more=False,
                )
            ),
        ) as mock_list_all:
            response = test_client.get("/api/content/all?ids=abc123&ids=def456")
    finally:
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 200
    assert mock_list_all.await_count == 1
    assert mock_list_all.await_args.kwargs["ids"] == ("abc123", "def456")


def test_all_files_endpoint_defaults_ids_filter_to_none(test_client):
    """Without ``ids`` query params the service receives ``None`` (no id filter)."""
    from main import app

    user = User(username="alice", groups=["users"])
    app.dependency_overrides[require_user] = lambda: user
    try:
        with patch(
            "services.content.stats.ContentStatsService.list_all_files",
            new=AsyncMock(
                return_value=FlatContentItemListResponse(
                    files=[],
                    total=0,
                    limit=50,
                    offset=0,
                    has_more=False,
                )
            ),
        ) as mock_list_all:
            response = test_client.get("/api/content/all")
    finally:
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 200
    assert mock_list_all.await_count == 1
    assert mock_list_all.await_args.kwargs["ids"] is None


def test_all_files_endpoint_passes_search_mode_filters_to_service(test_client):
    """The content-list endpoint should forward regex and path-search options."""
    from main import app

    user = User(username="alice", groups=["users"])
    app.dependency_overrides[require_user] = lambda: user
    try:
        with patch(
            "services.content.stats.ContentStatsService.list_all_files",
            new=AsyncMock(
                return_value=FlatContentItemListResponse(
                    files=[],
                    total=0,
                    limit=50,
                    offset=0,
                    has_more=False,
                )
            ),
        ) as mock_list_all:
            response = test_client.get(
                "/api/content/all?name=invoice-[0-9]%2B&name_regex=true&search_path=true"
            )
    finally:
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 200
    assert mock_list_all.await_count == 1
    assert mock_list_all.await_args.kwargs["name_contains"] == "invoice-[0-9]+"
    assert mock_list_all.await_args.kwargs["name_regex"] is True
    assert mock_list_all.await_args.kwargs["search_path"] is True


def test_all_files_endpoint_rejects_invalid_name_regex(test_client):
    """Invalid regex input should fail before the content-list query runs."""
    from main import app

    user = User(username="alice", groups=["users"])
    app.dependency_overrides[require_user] = lambda: user
    try:
        response = test_client.get("/api/content/all?name=(&name_regex=true")
    finally:
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 400
    assert "Invalid name regex" in response.json()["detail"]


def test_all_files_endpoint_passes_extraction_filters_to_service(test_client):
    """The content-list endpoint should forward extracted-field filters."""
    from main import app

    user = User(username="alice", groups=["users"])
    app.dependency_overrides[require_user] = lambda: user
    try:
        with patch(
            "services.content.stats.ContentStatsService.list_all_files",
            new=AsyncMock(
                return_value=FlatContentItemListResponse(
                    files=[],
                    total=0,
                    limit=50,
                    offset=0,
                    has_more=False,
                )
            ),
        ) as mock_list_all:
            response = test_client.get(
                "/api/content/all?extraction_field=invoice_number&extraction_value=RE-2026"
            )
    finally:
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 200
    assert mock_list_all.await_count == 1
    assert mock_list_all.await_args.kwargs["user"] is user
    assert mock_list_all.await_args.kwargs["extraction_field"] == "invoice_number"
    assert mock_list_all.await_args.kwargs["extraction_value"] == "RE-2026"


def test_all_files_endpoint_passes_structured_extraction_range_filters_to_service(
    test_client,
):
    """The content-list endpoint should forward numeric and date range filters."""
    from main import app

    user = User(username="alice", groups=["users"])
    app.dependency_overrides[require_user] = lambda: user
    try:
        with patch(
            "services.content.stats.ContentStatsService.list_all_files",
            new=AsyncMock(
                return_value=FlatContentItemListResponse(
                    files=[],
                    total=0,
                    limit=50,
                    offset=0,
                    has_more=False,
                )
            ),
        ) as mock_list_all:
            response = test_client.get(
                "/api/content/all?extraction_field=gross_amount"
                "&extraction_value_number_min=10.5"
                "&extraction_value_number_max=20"
                "&extraction_value_date_from=2026-04-01"
                "&extraction_value_date_to=2026-04-30"
            )
    finally:
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 200
    assert mock_list_all.await_count == 1
    assert mock_list_all.await_args.kwargs["user"] is user
    assert mock_list_all.await_args.kwargs["extraction_value_number_min"] == 10.5
    assert mock_list_all.await_args.kwargs["extraction_value_number_max"] == 20.0
    assert (
        mock_list_all.await_args.kwargs["extraction_value_date_from"].isoformat()
        == "2026-04-01"
    )
    assert (
        mock_list_all.await_args.kwargs["extraction_value_date_to"].isoformat()
        == "2026-04-30"
    )


def test_all_files_endpoint_passes_extraction_schema_filter_to_service(test_client):
    """The content-list endpoint should forward the extraction schema filter."""
    from main import app

    user = User(username="alice", groups=["users"])
    app.dependency_overrides[require_user] = lambda: user
    try:
        with patch(
            "services.content.stats.ContentStatsService.list_all_files",
            new=AsyncMock(
                return_value=FlatContentItemListResponse(
                    files=[],
                    total=0,
                    limit=50,
                    offset=0,
                    has_more=False,
                )
            ),
        ) as mock_list_all:
            response = test_client.get(
                "/api/content/all?extraction_schema=invoice_fields"
            )
    finally:
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 200
    assert mock_list_all.await_count == 1
    assert mock_list_all.await_args.kwargs["user"] is user
    assert mock_list_all.await_args.kwargs["extraction_schema"] == "invoice_fields"


def test_all_files_endpoint_passes_stale_enrichment_filter_to_service(test_client):
    """The content-list endpoint should forward the stale enrichment filter."""
    from main import app

    user = User(username="alice", groups=["users"])
    app.dependency_overrides[require_user] = lambda: user
    try:
        with patch(
            "services.content.stats.ContentStatsService.list_all_files",
            new=AsyncMock(
                return_value=FlatContentItemListResponse(
                    files=[],
                    total=0,
                    limit=50,
                    offset=0,
                    has_more=False,
                )
            ),
        ) as mock_list_all:
            response = test_client.get("/api/content/all?stale_enrichment=true")
    finally:
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 200
    assert mock_list_all.await_count == 1
    assert mock_list_all.await_args.kwargs["user"] is user
    assert mock_list_all.await_args.kwargs["stale_enrichment"] is True


def test_all_files_endpoint_passes_review_filters_to_service(test_client):
    """The content-list endpoint should forward enrichment review filters."""
    from main import app

    user = User(username="alice", groups=["users"])
    app.dependency_overrides[require_user] = lambda: user
    try:
        with patch(
            "services.content.stats.ContentStatsService.list_all_files",
            new=AsyncMock(
                return_value=FlatContentItemListResponse(
                    files=[],
                    total=0,
                    limit=50,
                    offset=0,
                    has_more=False,
                )
            ),
        ) as mock_list_all:
            response = test_client.get(
                "/api/content/all?needs_review=true&review_status=unreviewed"
            )
    finally:
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 200
    assert mock_list_all.await_count == 1
    assert mock_list_all.await_args.kwargs["user"] is user
    assert mock_list_all.await_args.kwargs["needs_review"] is True
    assert mock_list_all.await_args.kwargs["review_status"] == "unreviewed"


def test_all_files_endpoint_passes_review_reason_filter_to_service(test_client):
    """The content-list endpoint should forward enrichment review-reason filters."""
    from main import app

    user = User(username="alice", groups=["users"])
    app.dependency_overrides[require_user] = lambda: user
    try:
        with patch(
            "services.content.stats.ContentStatsService.list_all_files",
            new=AsyncMock(
                return_value=FlatContentItemListResponse(
                    files=[],
                    total=0,
                    limit=50,
                    offset=0,
                    has_more=False,
                )
            ),
        ) as mock_list_all:
            response = test_client.get(
                "/api/content/all?review_reason=missing_evidence"
            )
    finally:
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 200
    assert mock_list_all.await_count == 1
    assert mock_list_all.await_args.kwargs["user"] is user
    assert mock_list_all.await_args.kwargs["review_reason"] == "missing_evidence"


def test_all_files_endpoint_passes_review_priority_sort_to_service(test_client):
    """The content-list endpoint should allow and forward review-priority sorting."""
    from main import app

    user = User(username="alice", groups=["users"])
    app.dependency_overrides[require_user] = lambda: user
    try:
        with patch(
            "services.content.stats.ContentStatsService.list_all_files",
            new=AsyncMock(
                return_value=FlatContentItemListResponse(
                    files=[],
                    total=0,
                    limit=50,
                    offset=0,
                    has_more=False,
                )
            ),
        ) as mock_list_all:
            response = test_client.get(
                "/api/content/all?sort_by=review_priority&sort_order=asc"
            )
    finally:
        app.dependency_overrides.pop(require_user, None)

    assert response.status_code == 200
    assert mock_list_all.await_count == 1
    assert mock_list_all.await_args.kwargs["user"] is user
    assert mock_list_all.await_args.kwargs["sort_by"] == "review_priority"
    assert mock_list_all.await_args.kwargs["sort_order"] == "asc"
