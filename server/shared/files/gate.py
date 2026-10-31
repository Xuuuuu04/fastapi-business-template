import asyncio
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

from shared.access.caller import Caller
from shared.errors.framework import FileTooLarge, StepRuleBroken
from shared.files import artifacts
from shared.files.artifacts import ArtifactRef
from shared.files.storage import FileStorage, SavedFile, StoredObject
from shared.files.uploads import TempUpload, UploadArea


class ModuleFiles:
    def __init__(
        self, storage: FileStorage, uploads: UploadArea, module: str, caller: Caller | None = None
    ) -> None:
        self._storage = storage
        self._uploads = uploads
        self._prefix = f"{module}/"
        self._org = caller.org_id if caller else ""

    async def upload_info(self, temp_id: str) -> TempUpload:
        return (await self._uploads.find(temp_id))[1]

    async def read_upload(self, temp_id: str, max_bytes: int) -> bytes:
        if max_bytes < 0:
            raise ValueError("读取上限不能为负数")
        path, info = await self._uploads.find(temp_id)
        if info.size > max_bytes:
            raise FileTooLarge(f"文件超过读取上限 {max_bytes} 字节")
        return await asyncio.to_thread(read_bounded, path, max_bytes)

    async def discard_upload(self, temp_id: str) -> None:
        await self._uploads.discard(temp_id)

    async def save_bytes(self, key: str, content: bytes) -> SavedFile:
        self.mutable_key(key)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "content"
            await asyncio.to_thread(path.write_bytes, content)
            return await self._storage.save_path(self._full(key), path)

    async def exists(self, key: str) -> bool:
        return await self._storage.exists(self._full(key))

    async def adopt(self, temp_id: str, key: str) -> SavedFile:
        self.mutable_key(key)
        path, _ = await self._uploads.find(temp_id)
        saved = await self._storage.save_path(self._full(key), path)
        await self._uploads.discard(temp_id)
        return saved

    async def read(self, key: str, max_bytes: int) -> bytes:
        parts, size = [], 0
        async for chunk in self._storage.open(self._full(key)):
            size += len(chunk)
            if size > max_bytes:
                raise FileTooLarge(f"文件超过读取上限 {max_bytes} 字节")
            parts.append(chunk)
        return b"".join(parts)

    def open(self, key: str) -> AsyncIterator[bytes]:
        return self._storage.open(self._full(key))

    async def freeze(self, temp_id: str) -> ArtifactRef:
        path, _ = await self._uploads.find(temp_id)
        ref = await artifacts.freeze(self._storage, path, self._prefix, self._org)
        await self._uploads.discard(temp_id)
        return ref

    async def read_window(
        self, ref: ArtifactRef, offset: int, length: int, max_bytes: int = 1_000_000
    ) -> bytes:
        self.artifact_scope(ref)
        return await artifacts.window(self._storage, ref, offset, length, max_bytes)

    def open_artifact(self, ref: ArtifactRef) -> AsyncIterator[bytes]:
        self.artifact_scope(ref)
        return artifacts.stream(self._storage, ref)

    async def delete(self, key: str) -> None:
        await self._storage.delete(self._full(key))

    async def clean_uploads(self, older_than: float) -> int:
        return await self._uploads.clean(older_than)

    def list_objects(self) -> AsyncIterator[StoredObject]:
        return self._storage.list_objects(self._prefix)

    def _full(self, key: str) -> str:
        return key if key.startswith(self._prefix) else self._prefix + key

    def mutable_key(self, key: str) -> None:
        if self._full(key).startswith(self._prefix + "artifacts/"):
            raise StepRuleBroken("artifacts目录只能通过freeze写入，不允许覆盖原件")

    def artifact_scope(self, ref: ArtifactRef) -> None:
        if ref.key != artifacts.artifact_key(self._prefix, self._org, ref.sha256):
            raise StepRuleBroken("原件引用不属于当前模块与组织")


def read_bounded(path: Path, maximum: int) -> bytes:
    with path.open("rb") as source:
        content = source.read(maximum + 1)
    if len(content) > maximum:
        raise FileTooLarge(f"文件超过读取上限 {maximum} 字节")
    return content
