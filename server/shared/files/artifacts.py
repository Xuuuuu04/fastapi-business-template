import asyncio
import hashlib
import shutil
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated

from pydantic import Field, StringConstraints

from shared.data.fields import meaning
from shared.data.models import Data
from shared.errors.framework import FileTooLarge, StepRuleBroken
from shared.files.storage import FileStorage, digest_of


class ArtifactRef(Data):
    key: str = meaning("原始文件的存储路径，按模块和组织隔离")
    size: Annotated[int, Field(ge=0)] = meaning("原始文件的大小，单位为字节")
    sha256: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")] = meaning(
        "原始文件全部内容的 SHA-256 校验值"
    )


def artifact_key(prefix: str, org_id: str, digest: str) -> str:
    scope = hashlib.sha256(org_id.encode()).hexdigest()
    return f"{prefix}artifacts/{scope}/{digest}.bin"


async def freeze(storage: FileStorage, source: Path, prefix: str, org_id: str) -> ArtifactRef:
    with tempfile.TemporaryDirectory(prefix="artifact-snapshot-") as folder:
        snapshot = Path(folder) / "source"
        await asyncio.to_thread(shutil.copyfile, source, snapshot)
        size, digest = await digest_of(snapshot)
        ref = ArtifactRef(key=artifact_key(prefix, org_id, digest), size=size, sha256=digest)
        if await storage.exists(ref.key):
            await verify(storage, ref)
        else:
            saved = await storage.save_path(ref.key, snapshot)
            if (saved.size, saved.sha256) != (ref.size, ref.sha256):
                raise StepRuleBroken("保存后的原始文件与上传内容不一致")
    return ref


async def verify(storage: FileStorage, ref: ArtifactRef) -> None:
    digest, size = hashlib.sha256(), 0
    async for chunk in storage.open(ref.key):
        size += len(chunk)
        if size > ref.size:
            raise StepRuleBroken("原始文件的大小与保存的文件信息不一致")
        digest.update(chunk)
    if size != ref.size or digest.hexdigest() != ref.sha256:
        raise StepRuleBroken("原始文件的大小或 SHA-256 校验值与保存的文件信息不一致")


async def window(
    storage: FileStorage, ref: ArtifactRef, offset: int, length: int, max_bytes: int = 1_000_000
) -> bytes:
    if offset < 0 or length < 0 or offset + length > ref.size:
        raise StepRuleBroken("读取位置超出原始文件的范围")
    if length > max_bytes:
        raise FileTooLarge("本次读取的原始文件内容超过字节数上限")
    parts, size = [], 0
    async for chunk in storage.open_range(ref.key, offset, length):
        size += len(chunk)
        if size > length:
            raise StepRuleBroken("文件存储返回的内容超出本次指定的读取范围")
        parts.append(chunk)
    if size != length:
        raise StepRuleBroken("文件存储返回的内容少于本次指定的读取范围")
    return b"".join(parts)


async def stream(storage: FileStorage, ref: ArtifactRef) -> AsyncIterator[bytes]:
    digest, size = hashlib.sha256(), 0
    async for chunk in storage.open(ref.key):
        size += len(chunk)
        if size > ref.size:
            raise StepRuleBroken("原始文件超过保存时记录的大小")
        digest.update(chunk)
        yield chunk
    if size != ref.size or digest.hexdigest() != ref.sha256:
        raise StepRuleBroken("原始文件的内容与保存时记录的大小或校验值不一致")
