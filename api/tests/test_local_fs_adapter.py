"""Tests for local filesystem adapter path handling."""

import logging
from types import SimpleNamespace
import unicodedata
from io import BytesIO
from unittest.mock import patch

import pytest

from services.adapters.base import DataConnectorWriteTooLargeError
from services.adapters.local_fs import LocalFsAdapter


@pytest.mark.asyncio
async def test_list_directory_normalizes_unicode_paths(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    decomposed_name = "20230127_Cafe\u0301Report.pdf"
    (folder / decomposed_name).write_bytes(b"pdf")

    adapter = LocalFsAdapter(SimpleNamespace(path=str(tmp_path)))
    entries = await adapter.list_directory("docs")

    assert [entry.relative_path for entry in entries] == [
        "docs/20230127_CaféReport.pdf"
    ]
    assert entries[0].name == "20230127_CaféReport.pdf"
    assert (
        unicodedata.normalize("NFC", entries[0].relative_path)
        == entries[0].relative_path
    )


@pytest.mark.asyncio
async def test_read_file_resolves_normalized_unicode_path(tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "20230127_Cafe\u0301Report.pdf").write_bytes(b"content")

    adapter = LocalFsAdapter(SimpleNamespace(path=str(tmp_path)))

    entry = await adapter.stat("docs/20230127_CaféReport.pdf")
    stream = await adapter.read_file("docs/20230127_CaféReport.pdf")
    data = b"".join([chunk async for chunk in stream])

    assert entry.relative_path == "docs/20230127_CaféReport.pdf"
    assert data == b"content"


@pytest.mark.asyncio
async def test_write_file_reports_blocked_parent_path(tmp_path):
    folder = tmp_path / "inbox"
    folder.mkdir()
    (folder / "2026").write_bytes(b"not-a-directory")

    adapter = LocalFsAdapter(SimpleNamespace(path=str(tmp_path)))

    with pytest.raises(NotADirectoryError, match="Parent path is blocked"):
        await adapter.write_file("inbox/2026/05/09/file.pdf", BytesIO(b"content"))


@pytest.mark.asyncio
async def test_write_file_creates_full_nested_path_when_parent_is_missing(tmp_path):
    folder = tmp_path / "inbox"
    folder.mkdir()

    adapter = LocalFsAdapter(SimpleNamespace(path=str(tmp_path)))

    written = await adapter.write_file(
        "inbox/incoming/2026/05/09/file.pdf",
        BytesIO(b"content"),
    )
    entry = await adapter.stat("inbox/incoming/2026/05/09/file.pdf")

    assert written == len(b"content")
    assert entry.relative_path == "inbox/incoming/2026/05/09/file.pdf"
    written_path = tmp_path / "inbox" / "incoming" / "2026" / "05" / "09" / "file.pdf"
    assert written_path.read_bytes() == b"content"
    assert not (tmp_path / "inbox" / "incoming").is_file()


@pytest.mark.asyncio
async def test_write_file_rejects_oversized_payload_without_partial_file(tmp_path):
    adapter = LocalFsAdapter(SimpleNamespace(path=str(tmp_path)))

    with pytest.raises(DataConnectorWriteTooLargeError):
        await adapter.write_file("uploads/large.bin", BytesIO(b"012345"), max_bytes=5)

    assert not (tmp_path / "uploads" / "large.bin").exists()
    assert list((tmp_path / "uploads").iterdir()) == []


@pytest.mark.asyncio
async def test_read_file_yields_multiple_chunks_without_eager_buffering(
    tmp_path, monkeypatch
):
    (tmp_path / "large.txt").write_bytes(b"abcdefgh")
    monkeypatch.setattr("services.adapters.local_fs._READ_CHUNK_SIZE", 3)
    adapter = LocalFsAdapter(SimpleNamespace(path=str(tmp_path)))

    stream = await adapter.read_file("large.txt")

    assert [chunk async for chunk in stream] == [b"abc", b"def", b"gh"]


@pytest.mark.asyncio
async def test_list_directory_logs_scan_failures(tmp_path, caplog):
    adapter = LocalFsAdapter(SimpleNamespace(path=str(tmp_path)))
    caplog.set_level(logging.DEBUG, logger="services.adapters.local_fs")

    with patch("services.adapters.local_fs.os.scandir", side_effect=OSError("denied")):
        entries = await adapter.list_directory("")

    assert entries == []
    assert "Unable to scan local filesystem directory" in caplog.text
