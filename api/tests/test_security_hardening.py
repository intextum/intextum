"""Tests for preview and response hardening."""

from pathlib import Path

import pytest
from fastapi import HTTPException

from routers.content.browsing import _resolve_preview_media_type
from routers.content.extracted import _resolve_extracted_asset_media_type


def test_preview_rejects_active_html_content():
    with pytest.raises(HTTPException) as exc_info:
        _resolve_preview_media_type("report.html")

    assert exc_info.value.status_code == 415


def test_preview_rejects_svg_content():
    with pytest.raises(HTTPException) as exc_info:
        _resolve_preview_media_type("diagram.svg")

    assert exc_info.value.status_code == 415


def test_preview_allows_pdf():
    assert _resolve_preview_media_type("report.pdf") == "application/pdf"


def test_preview_allows_m4a_audio():
    assert _resolve_preview_media_type("recording.m4a") == "audio/mp4"


def test_extracted_asset_media_type_rejects_unsafe_content():
    with pytest.raises(HTTPException) as exc_info:
        _resolve_extracted_asset_media_type(Path("payload.html"))

    assert exc_info.value.status_code == 415


def test_extracted_asset_media_type_allows_png():
    assert _resolve_extracted_asset_media_type(Path("figure.png")) == "image/png"


def test_security_headers_are_attached_to_responses(test_client):
    response = test_client.get("/health/live")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "camera=()" in response.headers["Permissions-Policy"]
