"""Focused tests for worker backend client API helpers."""

from unittest.mock import MagicMock

import pytest
import requests

from intextum_worker.models import WorkerApiStatusResponse, WorkerClaimedTask
from intextum_worker.services.api_client_api import (
    build_worker_url,
    raise_for_status_with_detail,
    resolve_download_target,
    typed_json_response,
    typed_optional_json_response,
)


def test_build_worker_url_normalizes_trailing_slash():
    assert build_worker_url("http://localhost:8000/", "/api/worker/config") == (
        "http://localhost:8000/api/worker/config"
    )


def test_resolve_download_target_scopes_by_download_key(tmp_path):
    local_path = resolve_download_target(
        tmp_path,
        "docs/subdir/test.pdf",
        download_key="file-1",
    )

    assert local_path == tmp_path / "file-1" / "test.pdf"
    assert local_path.parent.is_dir()


def test_raise_for_status_with_detail_uses_backend_detail():
    response = MagicMock()
    response.request = MagicMock()
    response.text = ""
    response.json.return_value = {"detail": "Not allowed"}
    response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        "403 Client Error"
    )

    with pytest.raises(
        requests.exceptions.HTTPError, match="Backend detail: Not allowed"
    ):
        raise_for_status_with_detail(response)


def test_typed_json_response_validates_response_model():
    response = MagicMock()
    response.json.return_value = {"status": "ok"}

    result = typed_json_response(response, WorkerApiStatusResponse)

    assert result.status == "ok"
    response.raise_for_status.assert_called_once_with()


def test_typed_optional_json_response_returns_none_for_204():
    response = MagicMock()
    response.status_code = 204

    result = typed_optional_json_response(
        response,
        WorkerClaimedTask,
        none_status=204,
    )

    assert result is None
    response.raise_for_status.assert_not_called()
