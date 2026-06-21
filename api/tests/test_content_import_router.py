"""Tests for admin email-content import routes."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from auth.dependencies import require_admin
from models.content.items import ContentItemInfo, ContentItemKind, ContentItemType
from models.user import User


def _admin_user() -> User:
    return User(username="admin", sub="sub-admin", groups=["admins"])


def _imported_content_item() -> ContentItemInfo:
    return ContentItemInfo(
        id="mail-1",
        name="message.eml",
        display_name="Quarterly update",
        path="documents/Inbox/message.eml",
        kind=ContentItemKind.EMAIL_MESSAGE,
        type=ContentItemType.FILE,
        size_bytes=1024,
        size_human="1.0 kB",
        modified_at=datetime(2026, 4, 27, 12, 0, 0),
        is_hidden=False,
    )


def test_import_email_message_routes_to_ingestion_service(test_client):
    from main import app

    app.dependency_overrides[require_admin] = _admin_user
    try:
        with (
            patch(
                "routers.admin.content_imports.ConnectorRuntimeService.get_connector",
                return_value=SimpleNamespace(uuid="folder-documents", name="documents"),
            ),
            patch(
                "routers.admin.content_imports.ingest_email_message",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        content_item_id="mail-1",
                        attachment_content_item_ids=["attachment-1"],
                        task_id="task-mail-1",
                    )
                ),
            ) as ingest_email_message,
            patch(
                "routers.admin.content_imports.ContentService.get_file_details",
                new=AsyncMock(return_value=_imported_content_item()),
            ) as get_file_details,
        ):
            response = test_client.post(
                "/api/admin/content/import-email",
                json={
                    "connector_uuid": "folder-documents",
                    "relative_path": "Inbox/message.eml",
                    "subject": "Quarterly update",
                    "body_text": "Hello team",
                    "attachments": [
                        {
                            "relative_path": "Inbox/attachments/report.pdf",
                            "display_name": "report.pdf",
                        }
                    ],
                },
            )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["content_item"]["id"] == "mail-1"
    assert payload["attachment_content_item_ids"] == ["attachment-1"]
    assert payload["task_id"] == "task-mail-1"
    assert ingest_email_message.await_args.kwargs["subject"] == "Quarterly update"
    assert (
        ingest_email_message.await_args.kwargs["attachments"][0].display_name
        == "report.pdf"
    )
    assert ingest_email_message.await_args.kwargs["requested_by_sub"] == "sub-admin"
    assert get_file_details.await_args.args[0] == "documents/Inbox/message.eml"


def test_import_email_message_rejects_unknown_connector(test_client):
    from main import app

    app.dependency_overrides[require_admin] = _admin_user
    try:
        with patch(
            "routers.admin.content_imports.ConnectorRuntimeService.get_connector",
            return_value=None,
        ):
            response = test_client.post(
                "/api/admin/content/import-email",
                json={
                    "connector_uuid": "missing",
                    "relative_path": "Inbox/message.eml",
                },
            )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown data connector"
