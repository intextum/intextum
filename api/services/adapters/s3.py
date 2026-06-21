"""S3-compatible object-storage adapter for data sources."""

from __future__ import annotations

import logging
from contextlib import suppress
from pathlib import Path
from typing import AsyncIterator, BinaryIO, TYPE_CHECKING

import aiobotocore.session
from botocore.exceptions import ClientError

from .base import ContentEntry, DataConnectorAdapter, DataConnectorWriteTooLargeError

if TYPE_CHECKING:
    from models.connector_types import S3DataConnector

logger = logging.getLogger(__name__)

_READ_CHUNK_SIZE = 256 * 1024  # 256 KiB
_S3_MULTIPART_CHUNK_SIZE = 8 * 1024 * 1024  # S3 requires parts >= 5 MiB
_NOT_FOUND_ERROR_CODES = {"404", "NoSuchKey", "NotFound"}


def _is_not_found_error(exc: ClientError) -> bool:
    return exc.response.get("Error", {}).get("Code") in _NOT_FOUND_ERROR_CODES


class S3Adapter(DataConnectorAdapter):
    """Adapter that maps file operations to an S3-compatible bucket."""

    def __init__(self, source: S3DataConnector) -> None:
        self._source = source
        self._session = aiobotocore.session.get_session()

    def _full_key(self, rel_path: str) -> str:
        """Build the full S3 object key from a relative path."""
        cleaned = rel_path.strip("/")
        if self._source.s3_prefix and cleaned:
            return f"{self._source.s3_prefix}/{cleaned}"
        return self._source.s3_prefix or cleaned

    def _rel_from_key(self, key: str) -> str:
        """Strip the source prefix from an S3 key to get the relative path."""
        prefix = self._source.s3_prefix
        if prefix and key.startswith(prefix + "/"):
            return key[len(prefix) + 1 :]
        if prefix and key == prefix:
            return ""
        return key

    def _client_kwargs(self) -> dict:
        return {
            "service_name": "s3",
            "endpoint_url": self._source.endpoint_url,
            "region_name": self._source.region,
            "aws_access_key_id": self._source.access_key,
            "aws_secret_access_key": self._source.secret_key,
        }

    async def list_directory(self, rel_path: str) -> list[ContentEntry]:
        prefix = self._full_key(rel_path)
        if prefix and not prefix.endswith("/"):
            prefix += "/"

        entries: list[ContentEntry] = []
        async with self._session.create_client(**self._client_kwargs()) as client:
            paginator = client.get_paginator("list_objects_v2")
            async for page in paginator.paginate(
                Bucket=self._source.bucket,
                Prefix=prefix,
                Delimiter="/",
            ):
                for cp in page.get("CommonPrefixes", []):
                    dir_key = cp["Prefix"].rstrip("/")
                    rel = self._rel_from_key(dir_key)
                    name = rel.rsplit("/", 1)[-1] if "/" in rel else rel
                    if name.startswith("."):
                        continue
                    entries.append(
                        ContentEntry(
                            name=name,
                            relative_path=rel,
                            is_dir=True,
                            is_file=False,
                            is_symlink=False,
                            size_bytes=0,
                            modified_time=0,
                            change_time=0,
                        )
                    )
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if key == prefix:
                        continue
                    rel = self._rel_from_key(key)
                    name = rel.rsplit("/", 1)[-1] if "/" in rel else rel
                    if name.startswith("."):
                        continue
                    mtime = obj["LastModified"].timestamp()
                    entries.append(
                        ContentEntry(
                            name=name,
                            relative_path=rel,
                            is_dir=False,
                            is_file=True,
                            is_symlink=False,
                            size_bytes=obj.get("Size", 0),
                            modified_time=mtime,
                            change_time=mtime,
                        )
                    )
        return entries

    async def stat(self, rel_path: str) -> ContentEntry:
        key = self._full_key(rel_path)
        async with self._session.create_client(**self._client_kwargs()) as client:
            try:
                resp = await client.head_object(Bucket=self._source.bucket, Key=key)
                mtime = resp["LastModified"].timestamp()
                name = rel_path.rsplit("/", 1)[-1] if "/" in rel_path else rel_path
                return ContentEntry(
                    name=name or self._source.bucket,
                    relative_path=rel_path.strip("/"),
                    is_dir=False,
                    is_file=True,
                    is_symlink=False,
                    size_bytes=resp.get("ContentLength", 0),
                    modified_time=mtime,
                    change_time=mtime,
                )
            except ClientError as exc:
                if not _is_not_found_error(exc):
                    raise

            dir_prefix = key.rstrip("/") + "/" if key else ""
            resp = await client.list_objects_v2(
                Bucket=self._source.bucket,
                Prefix=dir_prefix,
                MaxKeys=1,
            )
            if resp.get("KeyCount", 0) > 0:
                name = rel_path.rsplit("/", 1)[-1] if "/" in rel_path else rel_path
                return ContentEntry(
                    name=name or self._source.bucket,
                    relative_path=rel_path.strip("/"),
                    is_dir=True,
                    is_file=False,
                    is_symlink=False,
                    size_bytes=0,
                    modified_time=0,
                    change_time=0,
                )

        raise FileNotFoundError(rel_path)

    async def exists(self, rel_path: str) -> bool:
        try:
            await self.stat(rel_path)
            return True
        except FileNotFoundError:
            return False

    async def is_dir(self, rel_path: str) -> bool:
        try:
            entry = await self.stat(rel_path)
            return entry.is_dir
        except FileNotFoundError:
            return False

    async def is_file(self, rel_path: str) -> bool:
        try:
            entry = await self.stat(rel_path)
            return entry.is_file
        except FileNotFoundError:
            return False

    async def read_file(self, rel_path: str) -> AsyncIterator[bytes]:
        key = self._full_key(rel_path)

        async def _stream() -> AsyncIterator[bytes]:
            async with self._session.create_client(**self._client_kwargs()) as client:
                try:
                    resp = await client.get_object(Bucket=self._source.bucket, Key=key)
                except ClientError as exc:
                    if _is_not_found_error(exc):
                        raise FileNotFoundError(rel_path)
                    raise
                async for chunk in resp["Body"].iter_chunks(
                    chunk_size=_READ_CHUNK_SIZE
                ):
                    yield chunk

        return _stream()

    async def write_file(
        self, rel_path: str, data: BinaryIO, *, max_bytes: int | None = None
    ) -> int:
        key = self._full_key(rel_path)
        written = 0
        pending = bytearray()
        upload_id: str | None = None
        parts: list[dict[str, object]] = []

        async with self._session.create_client(**self._client_kwargs()) as client:
            try:

                async def _flush_part(body: bytes) -> None:
                    nonlocal upload_id
                    if upload_id is None:
                        response = await client.create_multipart_upload(
                            Bucket=self._source.bucket,
                            Key=key,
                        )
                        upload_id = response["UploadId"]
                    part_number = len(parts) + 1
                    response = await client.upload_part(
                        Bucket=self._source.bucket,
                        Key=key,
                        UploadId=upload_id,
                        PartNumber=part_number,
                        Body=body,
                    )
                    parts.append(
                        {
                            "ETag": response.get("ETag", ""),
                            "PartNumber": part_number,
                        }
                    )

                while True:
                    chunk = data.read(_READ_CHUNK_SIZE)
                    if not chunk:
                        break
                    next_written = written + len(chunk)
                    if max_bytes is not None and next_written > max_bytes:
                        raise DataConnectorWriteTooLargeError(max_bytes)
                    written = next_written
                    pending.extend(chunk)
                    if len(pending) >= _S3_MULTIPART_CHUNK_SIZE:
                        await _flush_part(bytes(pending))
                        pending.clear()

                if upload_id is None:
                    await client.put_object(
                        Bucket=self._source.bucket,
                        Key=key,
                        Body=bytes(pending),
                    )
                else:
                    if pending:
                        await _flush_part(bytes(pending))
                    await client.complete_multipart_upload(
                        Bucket=self._source.bucket,
                        Key=key,
                        UploadId=upload_id,
                        MultipartUpload={"Parts": parts},
                    )
            except Exception:
                if upload_id is not None:
                    with suppress(Exception):
                        await client.abort_multipart_upload(
                            Bucket=self._source.bucket,
                            Key=key,
                            UploadId=upload_id,
                        )
                raise
        return written

    async def create_directory(self, rel_path: str) -> None:
        key = self._full_key(rel_path).rstrip("/") + "/"
        async with self._session.create_client(**self._client_kwargs()) as client:
            await client.put_object(
                Bucket=self._source.bucket,
                Key=key,
                Body=b"",
            )

    async def delete(self, rel_path: str) -> None:
        key = self._full_key(rel_path)
        async with self._session.create_client(**self._client_kwargs()) as client:
            try:
                await client.head_object(Bucket=self._source.bucket, Key=key)
                await client.delete_object(Bucket=self._source.bucket, Key=key)
                return
            except ClientError as exc:
                if not _is_not_found_error(exc):
                    raise
            dir_key = key.rstrip("/") + "/"
            try:
                await client.head_object(Bucket=self._source.bucket, Key=dir_key)
                await client.delete_object(Bucket=self._source.bucket, Key=dir_key)
                return
            except ClientError as exc:
                if not _is_not_found_error(exc):
                    raise
            raise FileNotFoundError(rel_path)

    async def get_local_path(self, _rel_path: str) -> Path | None:
        return None
