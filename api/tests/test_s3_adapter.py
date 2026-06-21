"""Tests for S3 adapter error handling."""

from io import BytesIO
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError

from services.adapters.base import DataConnectorWriteTooLargeError
from services.adapters.s3 import S3Adapter


def _source():
    return SimpleNamespace(
        bucket="bucket",
        s3_prefix="prefix",
        endpoint_url="http://s3.test",
        region="eu-central-1",
        access_key="access",
        secret_key="secret",
    )


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code}}, "HeadObject")


class FakeS3Client:
    def __init__(self, *, head_results=()):
        self._head_results = list(head_results)
        self.deleted_keys: list[str] = []
        self.put_objects: list[dict] = []
        self.multipart_parts: list[dict] = []
        self.completed_uploads: list[dict] = []
        self.aborted_uploads: list[dict] = []

    async def head_object(self, *, Bucket, Key):
        result = self._head_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def delete_object(self, *, Bucket, Key):
        self.deleted_keys.append(Key)

    async def put_object(self, *, Bucket, Key, Body):
        self.put_objects.append({"Bucket": Bucket, "Key": Key, "Body": Body})

    async def create_multipart_upload(self, *, Bucket, Key):
        return {"UploadId": "upload-1"}

    async def upload_part(self, *, Bucket, Key, UploadId, PartNumber, Body):
        self.multipart_parts.append(
            {
                "Bucket": Bucket,
                "Key": Key,
                "UploadId": UploadId,
                "PartNumber": PartNumber,
                "Body": Body,
            }
        )
        return {"ETag": f"etag-{PartNumber}"}

    async def complete_multipart_upload(
        self, *, Bucket, Key, UploadId, MultipartUpload
    ):
        self.completed_uploads.append(
            {
                "Bucket": Bucket,
                "Key": Key,
                "UploadId": UploadId,
                "MultipartUpload": MultipartUpload,
            }
        )

    async def abort_multipart_upload(self, *, Bucket, Key, UploadId):
        self.aborted_uploads.append(
            {"Bucket": Bucket, "Key": Key, "UploadId": UploadId}
        )


class FakeS3ClientContext:
    def __init__(self, client):
        self._client = client

    async def __aenter__(self):
        return self._client

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeS3Session:
    def __init__(self, client):
        self._client = client

    def create_client(self, **_kwargs):
        return FakeS3ClientContext(self._client)


def _adapter_with_client(client: FakeS3Client) -> S3Adapter:
    adapter = S3Adapter(_source())
    adapter._session = FakeS3Session(client)
    return adapter


@pytest.mark.asyncio
async def test_delete_propagates_non_not_found_head_errors():
    client = FakeS3Client(head_results=[_client_error("AccessDenied")])
    adapter = _adapter_with_client(client)

    with pytest.raises(ClientError):
        await adapter.delete("docs/file.pdf")

    assert client.deleted_keys == []


@pytest.mark.asyncio
async def test_delete_removes_directory_marker_after_missing_object_key():
    client = FakeS3Client(head_results=[_client_error("404"), {}])
    adapter = _adapter_with_client(client)

    await adapter.delete("docs")

    assert client.deleted_keys == ["prefix/docs/"]


class NoFullReadStream(BytesIO):
    """BytesIO that fails if adapter tries to read the whole body at once."""

    def read(self, size=-1):
        if size is None or size < 0:
            raise AssertionError("stream must be read in bounded chunks")
        return super().read(size)


@pytest.mark.asyncio
async def test_write_file_reads_bounded_chunks_for_small_objects():
    client = FakeS3Client()
    adapter = _adapter_with_client(client)

    written = await adapter.write_file("docs/file.txt", NoFullReadStream(b"content"))

    assert written == len(b"content")
    assert client.put_objects == [
        {"Bucket": "bucket", "Key": "prefix/docs/file.txt", "Body": b"content"}
    ]


@pytest.mark.asyncio
async def test_write_file_rejects_oversized_payload_before_put_object():
    client = FakeS3Client()
    adapter = _adapter_with_client(client)

    with pytest.raises(DataConnectorWriteTooLargeError):
        await adapter.write_file(
            "docs/large.bin",
            NoFullReadStream(b"012345"),
            max_bytes=5,
        )

    assert client.put_objects == []
    assert client.completed_uploads == []
