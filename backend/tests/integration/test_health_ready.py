"""Integration tests for readiness endpoint with real dependencies."""

import pytest


@pytest.mark.integration
def test_health_ready_reports_ok_with_running_dependencies(integration_client):
    """Readiness should be green when Postgres is reachable."""
    response = integration_client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "components": {
            "postgres": "ok",
        },
    }
