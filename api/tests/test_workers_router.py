"""Tests for worker management router dependencies."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from models.user import User
from routers.workers import get_worker_service
from version import get_app_version


def test_install_info_returns_package_version_and_platforms(test_client):
    with patch(
        "routers.workers.GeneralSettingsService.get_public_base_url",
        new=AsyncMock(return_value="https://dms.example.org"),
    ):
        response = test_client.get("/api/workers/install-info")

    assert response.status_code == 200
    payload = response.json()

    assert payload["package"] == "intextum-worker"
    assert payload["version"] == get_app_version()
    assert payload["default_capabilities"] == "document,video,image"
    # The configured public base URL is surfaced for the install command.
    assert payload["public_url"] == "https://dms.example.org"

    platforms = {p["id"]: p for p in payload["platforms"]}
    assert set(platforms) == {
        "macos-mps",
        "linux-cpu",
        "linux-cuda",
        "windows-cpu",
        "windows-cuda",
        "docker-cpu",
        "docker-cuda",
    }

    # macOS Torch wheels are on PyPI -> pip install, no extra index needed.
    assert platforms["macos-mps"]["kind"] == "pip"
    assert platforms["macos-mps"]["extra"] == "mps"
    assert platforms["macos-mps"]["extra_index_url"] is None

    # Linux/Windows CPU/CUDA pull their Torch build from the PyTorch index.
    assert (
        platforms["linux-cpu"]["extra_index_url"]
        == "https://download.pytorch.org/whl/cpu"
    )
    assert (
        platforms["windows-cuda"]["extra_index_url"]
        == "https://download.pytorch.org/whl/cu126"
    )

    # Docker targets reference the prebuilt GHCR images; CUDA requests the GPU.
    assert platforms["docker-cpu"]["kind"] == "docker"
    assert platforms["docker-cpu"]["image"] == "ghcr.io/intextum/intextum/worker-cpu"
    assert platforms["docker-cuda"]["gpu"] is True


def test_install_info_path_not_captured_as_worker_id(test_client):
    # The static /install-info route must win over /{worker_id}; a 200 (not a
    # worker lookup) confirms route ordering is correct.
    response = test_client.get("/api/workers/install-info")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_worker_service_dependency_applies_admin_rls_context():
    db = SimpleNamespace(
        sync_session=SimpleNamespace(info={}),
        execute=AsyncMock(),
    )
    admin = User(
        username="admin",
        sub="sub-admin",
        groups=["admins"],
        is_admin=True,
    )

    service = await get_worker_service(user=admin, db=db)  # type: ignore[arg-type]

    assert service.db is db
    sql, params = db.execute.await_args.args
    assert "set_config('app.actor'" in str(sql)
    assert params["actor"] == "user"
    assert params["is_admin"] == "true"
