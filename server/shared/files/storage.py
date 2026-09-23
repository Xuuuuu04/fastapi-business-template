"""
文件存储的统一约定 FileStorage 和两个实现：本地目录 LocalFiles、S3 兼容存储 S3Files。
S3Files 可用于 MinIO 和各云对象存储。
只负责按键保存和读取文件内容；文件记录、权限和业务含义由文件管理模块负责。
键只能包含字母、数字、斜线、下划线、点和短横线，不能包含“..”，防止写到存储目录以外。
"""

import asyncio
import hashlib
import re
import shutil
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import anyio
import boto3  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

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
    # 把本地文件保存到存储中的指定键。
    async def save_path(self, key: str, source: Path) -> SavedFile: ...

    # 按块读取文件内容。
    def open(self, key: str) -> AsyncIterator[bytes]: ...

    # 删除文件；文件不存在时不报错。
    async def delete(self, key: str) -> None: ...

    # 判断文件是否存在。
    async def exists(self, key: str) -> bool: ...

    # 按前缀逐项列出对象，供后台清理没有文件记录的孤立对象。
    def list_objects(self, prefix: str) -> AsyncIterator[StoredObject]: ...


# 检查存储键的格式。
def check_key(key: str) -> str:
    if not KEY.match(key) or ".." in key:
        raise StepRuleBroken(f"文件存储键 {key} 格式不正确")
    return key


# 计算本地文件的大小和 SHA-256。
async def digest_of(path: Path) -> tuple[int, str]:
    digest, size = hashlib.sha256(), 0
    async with await anyio.open_file(path, "rb") as source:
        while chunk := await source.read(CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


class LocalFiles:
    # 使用本地目录保存文件。
    def __init__(self, root: Path) -> None:
        self.root = root

    # 复制到存储目录：先写临时文件再改名，读取方不会看到写了一半的文件。
    async def save_path(self, key: str, source: Path) -> SavedFile:
        target = self.root / check_key(key)
        partial = target.with_name(target.name + ".partial")
        await anyio.Path(target.parent).mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copyfile, source, partial)
        await anyio.Path(partial).rename(target)
        size, digest = await digest_of(target)
        return SavedFile(key, size, digest)

    # 按块读取文件内容。
    async def open(self, key: str) -> AsyncIterator[bytes]:
        async with await anyio.open_file(self.root / check_key(key), "rb") as source:
            while chunk := await source.read(CHUNK):
                yield chunk

    # 删除文件。
    async def delete(self, key: str) -> None:
        await anyio.Path(self.root / check_key(key)).unlink(missing_ok=True)

    # 判断文件是否存在。
    async def exists(self, key: str) -> bool:
        return await anyio.Path(self.root / check_key(key)).is_file()

    # 按目录逐项扫描，不把所有文件一次放进内存。
    async def list_objects(self, prefix: str) -> AsyncIterator[StoredObject]:
        folder = anyio.Path(self.root / check_key(prefix.rstrip("/")))
        if not await folder.is_dir():
            return
        async for item in walk_files(folder):
            key = item.relative_to(self.root).as_posix()
            if not key.endswith(".partial"):
                yield StoredObject(key, (await item.stat()).st_mtime)


# 递归列出本地目录中的文件，避免一次读取全部目录项。
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
    # 使用 S3 兼容存储；boto3 是同步库，所有调用放到线程中执行。
    def __init__(self, options: S3Options) -> None:
        self.bucket = options.bucket
        self.client: Any = boto3.client(
            "s3",
            endpoint_url=options.endpoint or None,
            region_name=options.region or None,
            aws_access_key_id=options.access_key or None,
            aws_secret_access_key=options.secret_key or None,
        )

    # 上传本地文件；大文件由 boto3 自动分片。
    async def save_path(self, key: str, source: Path) -> SavedFile:
        size, digest = await digest_of(source)
        await asyncio.to_thread(self.client.upload_file, str(source), self.bucket, check_key(key))
        return SavedFile(key, size, digest)

    # 按块读取对象内容。
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

    # 删除对象。
    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=check_key(key))

    # 判断对象是否存在。
    async def exists(self, key: str) -> bool:
        try:
            await asyncio.to_thread(self.client.head_object, Bucket=self.bucket, Key=check_key(key))
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code in ("404", "NoSuchKey", "NotFound"):
                return False
            raise
        return True

    # 按 S3 分页逐项列出指定模块的对象。
    async def list_objects(self, prefix: str) -> AsyncIterator[StoredObject]:
        params: dict[str, Any] = {"Bucket": self.bucket, "Prefix": check_key(prefix)}
        while True:
            reply = await asyncio.to_thread(self.client.list_objects_v2, **params)
            for item in reply.get("Contents", []):
                yield StoredObject(item["Key"], item["LastModified"].timestamp())
            if not reply.get("IsTruncated"):
                break
            params["ContinuationToken"] = reply["NextContinuationToken"]
