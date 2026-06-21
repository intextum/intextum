"""Tests for browser-side error reporting routes."""

from unittest.mock import patch


def test_client_error_report_is_logged(test_client):
    payload = {
        "message": "Maximum update depth exceeded",
        "name": "Error",
        "stack": "stack",
        "component_stack": "component stack",
        "route_name": "content-item",
        "href": "http://localhost/content/item/demo",
        "user_agent": "pytest",
    }

    with patch("routers.client_errors.logger.error") as log_error:
        response = test_client.post("/api/client-errors", json=payload)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    log_error.assert_called_once()
    assert log_error.call_args.args == ("Client error reported",)
    assert log_error.call_args.kwargs["extra"]["route_name"] == "content-item"
    assert log_error.call_args.kwargs["extra"]["error_message"] == (
        "Maximum update depth exceeded"
    )
