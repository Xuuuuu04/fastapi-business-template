"""
不可变原件引用与有界窗口读取，原件只冻结一次，后续批次按位置读取而非重新加载全文。
"""

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


# 引用只携带存储键、完整摘要和大小，不把原件正文复制进任务或检查记录。
class ArtifactRef(Data):
    key: str = meaning("不可变原件的模块与组织存储键")
    size: Annotated[int, Field(ge=0)] = meaning("原件字节数")
    sha256: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")] = meaning("完整内容摘要")


# 组织边界不读取业务输入的自报组织，来自已经确认的调用者上下文。
def artifact_key(prefix: str, org_id: str, digest: str) -> str:
    scope = hashlib.sha256(org_id.encode()).hexdigest()
    return f"{prefix}artifacts/{scope}/{digest}.bin"


# 冻结私有快照后按内容摘要存储，同内容并发提交仍指向同一原件。
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
                raise StepRuleBroken("存储保存的原件与冻结快照不一致")
    return ref


# 已存在的摘要键先核对完整内容，不用存在这个事实推定原件没有被改变。
async def verify(storage: FileStorage, ref: ArtifactRef) -> None:
    digest, size = hashlib.sha256(), 0
    async for chunk in storage.open(ref.key):
        size += len(chunk)
        if size > ref.size:
            raise StepRuleBroken("不可变原件大小与引用不一致")
        digest.update(chunk)
    if size != ref.size or digest.hexdigest() != ref.sha256:
        raise StepRuleBroken("不可变原件摘要与引用不一致")


# 读取一批有界内容，不从零读取前面的所有字节。
async def window(
    storage: FileStorage, ref: ArtifactRef, offset: int, length: int, max_bytes: int = 1_000_000
) -> bytes:
    if offset < 0 or length < 0 or offset + length > ref.size:
        raise StepRuleBroken("原件窗口位置超出引用范围")
    if length > max_bytes:
        raise FileTooLarge("原件窗口超过本批字节上限")
    parts, size = [], 0
    async for chunk in storage.open_range(ref.key, offset, length):
        size += len(chunk)
        if size > length:
            raise StepRuleBroken("存储返回超过声明窗口的内容")
        parts.append(chunk)
    if size != length:
        raise StepRuleBroken("存储返回的原件窗口不完整")
    return b"".join(parts)


# 流式读取在完成时核对完整摘要，发布最终业务结果前必须消费到结尾。
async def stream(storage: FileStorage, ref: ArtifactRef) -> AsyncIterator[bytes]:
    digest, size = hashlib.sha256(), 0
    async for chunk in storage.open(ref.key):
        size += len(chunk)
        if size > ref.size:
            raise StepRuleBroken("原件超过已冻结大小")
        digest.update(chunk)
        yield chunk
    if size != ref.size or digest.hexdigest() != ref.sha256:
        raise StepRuleBroken("原件内容与已冻结引用不一致")
