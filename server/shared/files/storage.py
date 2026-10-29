import asyncio
import hashlib
import re
import secrets
import shutil
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import anyio
import boto3
from botocore.exceptions import ClientError

from shared.errors.framework import StepRuleBroken

CHUNK = 64 * 1024
KEY = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]*$")


@dataclass(frozen=True)
class SavedFile:
    key: str
    size: int
    sha256: str


@dataclass(frozen=True)
class StoredObject:
    key: str
    modified_at: float


class FileStorage(Protocol):
    async def save_path(self, key: str, source: Path) -> SavedFile: ...

    def open(self, key: str) -> AsyncIterator[bytes]: ...

    def open_range(self, key: str, offset: int, length: int) -> AsyncIterator[bytes]: ...

    async def delete(self, key: str) -> None: ...

    async def exists(self, key: str) -> bool: ...

    def list_objects(self, prefix: str) -> AsyncIterator[StoredObject]: ...


def check_key(key: str) -> str:
    if not KEY.match(key) or ".." in key:
        raise StepRuleBroken(f"文件存储键 {key} 格式不正确")
    return key


async def digest_of(path: Path) -> tuple[int, str]:
    digest, size = hashlib.sha256(), 0
    async with await anyio.open_file(path, "rb") as source:
        while chunk := await source.read(CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


class LocalFiles:
    def __init__(self, root: Path) -> None:
        self.root = root

    async def save_path(self, key: str, source: Path) -> SavedFile:
        target = self.root / check_key(key)
        partial = target.with_name(target.name + "." + secrets.token_hex(8) + ".partial")
        await anyio.Path(target.parent).mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copyfile, source, partial)
        await anyio.Path(partial).rename(target)
        size, digest = await digest_of(target)
        return SavedFile(key, size, digest)

    async def open(self, key: str) -> AsyncIterator[bytes]:
        async with await anyio.open_file(self.root / check_key(key), "rb") as source:
            while chunk := await source.read(CHUNK):
                yield chunk

    async def open_range(self, key: str, offset: int, length: int) -> AsyncIterator[bytes]:
        if offset < 0 or length < 0:
            raise StepRuleBroken("文件窗口不能为负数")
        async with await anyio.open_file(self.root / check_key(key), "rb") as source:
            await source.seek(offset)
            remaining = length
            while remaining:
                chunk = await source.read(min(CHUNK, remaining))
                if not chunk:
                    return
                remaining -= len(chunk)
                yield chunk

    async def delete(self, key: str) -> None:
        await anyio.Path(self.root / check_key(key)).unlink(missing_ok=True)

    async def exists(self, key: str) -> bool:
        return await anyio.Path(self.root / check_key(key)).is_file()

    async def list_objects(self, prefix: str) -> AsyncIterator[StoredObject]:
        folder = anyio.Path(self.root / check_key(prefix.rstrip("/")))
        if not await folder.is_dir():
            return
        async for item in walk_files(folder):
            key = item.relative_to(self.root).as_posix()
            if not key.endswith(".partial"):
                yield StoredObject(key, (await item.stat()).st_mtime)


async def walk_files(folder: anyio.Path) -> AsyncIterator[anyio.Path]:
    async for item in folder.iterdir():
        if await item.is_dir():
            async for child in walk_files(item):
                yield child
        elif await item.is_file():
            yield item


@dataclass(frozen=True)
class S3Options:
    bucket: str
    endpoint: str
    region: str
    access_key: str
    secret_key: str


class S3Files:
    def __init__(self, options: S3Options) -> None:
        self.bucket = options.bucket
        self.client: Any = boto3.client(
            "s3",
            endpoint_url=options.endpoint or None,
            region_name=options.region or None,
            aws_access_key_id=options.access_key or None,
            aws_secret_access_key=options.secret_key or None,
        )

    async def save_path(self, key: str, source: Path) -> SavedFile:
        size, digest = await digest_of(source)
        await asyncio.to_thread(self.client.upload_file, str(source), self.bucket, check_key(key))
        return SavedFile(key, size, digest)

    async def open(self, key: str) -> AsyncIterator[bytes]:
        reply = await asyncio.to_thread(
            self.client.get_object, Bucket=self.bucket, Key=check_key(key)
        )
        body = reply["Body"]
        try:
            while chunk := await asyncio.to_thread(body.read, CHUNK):
                yield chunk
        finally:
            body.close()

    async def open_range(self, key: str, offset: int, length: int) -> AsyncIterator[bytes]:
        if offset < 0 or length < 0:
            raise StepRuleBroken("文件窗口不能为负数")
        if not length:
            return
        reply = await asyncio.to_thread(
            self.client.get_object,
            Bucket=self.bucket,
            Key=check_key(key),
            Range=f"bytes={offset}-{offset + length - 1}",
        )
        body = reply["Body"]
        try:
            expected = f"bytes {offset}-{offset + length - 1}/"
            if (
                not str(reply.get("ContentRange", "")).startswith(expected)
                or reply.get("ContentLength") != length
            ):
                raise StepRuleBroken("S3没有返回已声明的有界范围")
            remaining = length
            while remaining:
                chunk = await asyncio.to_thread(body.read, min(CHUNK, remaining))
                if not chunk:
                    return
                remaining -= len(chunk)
                yield chunk
        finally:
            body.close()

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=check_key(key))

    async def exists(self, key: str) -> bool:
        try:
            await asyncio.to_thread(self.client.head_object, Bucket=self.bucket, Key=check_key(key))
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code in ("404", "NoSuchKey", "NotFound"):
                return False
            raise
        return True

    async def list_objects(self, prefix: str) -> AsyncIterator[StoredObject]:
        params: dict[str, Any] = {"Bucket": self.bucket, "Prefix": check_key(prefix)}
        while True:
            reply = await asyncio.to_thread(self.client.list_objects_v2, **params)
            for item in reply.get("Contents", []):
                yield StoredObject(item["Key"], item["LastModified"].timestamp())
            if not reply.get("IsTruncated"):
                break
            params["ContinuationToken"] = reply["NextContinuationToken"]
