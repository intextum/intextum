"""Tests for worker bearer token authentication dependency."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from auth.worker_auth import require_worker_token


@pytest.mark.asyncio
async def test_require_worker_token_returns_worker_id_and_updates_last_seen():
    """Valid token should return worker_id and update last_seen timestamp."""
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token-1")
    db = AsyncMock()

    mock_service = AsyncMock()
    mock_service.validate_token.return_value = "worker-1"

    with patch("auth.worker_auth.WorkerService", return_value=mock_service):
        worker_id = await require_worker_token(credentials=creds, db=db)

    assert worker_id == "worker-1"
    mock_service.validate_token.assert_awaited_once_with("token-1")
    mock_service.update_last_seen.assert_awaited_once_with("worker-1")


@pytest.mark.asyncio
async def test_require_worker_token_raises_401_for_invalid_token():
    """Invalid token should return HTTP 401 and avoid touching last_seen."""
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad-token")
    db = AsyncMock()

    mock_service = AsyncMock()
    mock_service.validate_token.return_value = None

    with patch("auth.worker_auth.WorkerService", return_value=mock_service):
        with pytest.raises(HTTPException) as exc_info:
            await require_worker_token(credentials=creds, db=db)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid or revoked worker token"
    mock_service.update_last_seen.assert_not_called()
