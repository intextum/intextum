"""Focused tests for worker backend client upload helpers."""

from unittest.mock import MagicMock

from services.api_client_uploads import upload_extracted_directory


def test_upload_extracted_directory_batches_and_aggregates(tmp_path):
    session = MagicMock()
    first_response = MagicMock()
    first_response.json.return_value = {
        "status": "ok",
        "content_item_id": "file-1",
        "uploaded": 1,
        "files": [{"path": "pages/page-1.png", "size": 4}],
    }
    second_response = MagicMock()
    second_response.json.return_value = {
        "status": "ok",
        "content_item_id": "file-1",
        "uploaded": 1,
        "files": [{"path": "pages/page-2.png", "size": 5}],
    }
    session.post.side_effect = [first_response, second_response]

    local_dir = tmp_path / "output"
    local_dir.mkdir()
    (local_dir / "page-1.png").write_bytes(b"data")
    (local_dir / "page-2.png").write_bytes(b"data2")

    result = upload_extracted_directory(
        session,
        "http://localhost:8000",
        "file-1",
        local_dir,
        "task-1",
        "secret-1",
        timeout=(10, 120),
        batch_size=1,
    )

    assert result.content_item_id == "file-1"
    assert result.uploaded == 2
    assert [file.path for file in result.files] == [
        "pages/page-1.png",
        "pages/page-2.png",
    ]
    assert len(result.batches) == 2
    assert session.post.call_count == 2
    assert session.post.call_args_list[0].kwargs["headers"] == {
        "X-Task-Id": "task-1",
        "X-Task-Secret": "secret-1",
    }
