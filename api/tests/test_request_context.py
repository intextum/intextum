"""Unit tests for the request-to-RLS-context routing in database.py."""

from __future__ import annotations

from types import SimpleNamespace

from database import _request_context
from models.user import User


def _request(path: str, user: User | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        url=SimpleNamespace(path=path),
        state=SimpleNamespace(current_user=user),
    )


def test_request_context_auth_prefix_picks_auth_actor():
    context = _request_context(_request("/api/auth/login"))
    assert context.actor == "auth"


def test_request_context_worker_prefix_picks_worker_claim_actor():
    context = _request_context(_request("/api/worker/tasks/claim"))
    assert context.actor == "worker_claim"


def test_request_context_workers_admin_path_does_not_match_worker_claim():
    """The admin /api/workers/... router must not be routed as a worker_claim.

    Regression test for the /api/worker vs /api/workers prefix collision.
    """
    user = User(username="alice", sub="app:alice", groups=["users"])
    context = _request_context(_request("/api/workers/123", user=user))
    assert context.actor == "user"
    assert context.user_sub == "app:alice"


def test_request_context_auth_lookalike_path_does_not_match_auth():
    user = User(username="alice", sub="app:alice", groups=["users"])
    context = _request_context(_request("/api/authentication", user=user))
    assert context.actor == "user"


def test_request_context_user_path_with_authenticated_user_returns_user():
    user = User(username="alice", sub="app:alice", groups=["users"], is_admin=False)
    context = _request_context(_request("/api/content/items", user=user))
    assert context.actor == "user"
    assert context.user_sub == "app:alice"
    assert "sub:app:alice" in context.trustees


def test_request_context_unauthenticated_request_returns_anonymous():
    context = _request_context(_request("/api/content/items"))
    assert context.actor == "anonymous"
    assert context.user_sub == ""
