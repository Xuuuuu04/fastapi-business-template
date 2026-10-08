"""
模块的存储实现拿到的 files 参数 ModuleFiles：存储键自动加上模块名前缀，
提供“把临时上传保存为正式文件”“读取”“删除”三类操作。
"""

import asyncio
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

from shared.errors.framework import FileTooLarge
from shared.files.storage import FileStorage, SavedFile, StoredObject
from shared.files.uploads import TempUpload, UploadArea


# 模块使用的文件入口，把存储键限定在模块自己的目录范围内。
class ModuleFiles:
    # 绑定存储、上传临时区和模块名。
    def __init__(self, storage: FileStorage, uploads: UploadArea, module: str) -> None:
        self._storage = storage
        self._uploads = uploads
        self._prefix = f"{module}/"

    # 读取临时上传的信息，不移动文件。
    async def upload_info(self, temp_id: str) -> TempUpload:
        return (await self._uploads.find(temp_id))[1]

    # 有界读取临时上传，检查时不移动原件，避免先读取整文件再判断上限。
    async def read_upload(self, temp_id: str, max_bytes: int) -> bytes:
        if max_bytes < 0:
            raise ValueError("读取上限不能为负数")
        path, info = await self._uploads.find(temp_id)
        if info.size > max_bytes:
            raise FileTooLarge(f"文件超过读取上限 {max_bytes} 字节")
        return await asyncio.to_thread(read_bounded, path, max_bytes)

    # 清理已经由业务明确判为重复的临时上传。
    async def discard_upload(self, temp_id: str) -> None:
        await self._uploads.discard(temp_id)

    # 保存业务生成的文件，临时磁盘写入不占用事件循环。
    async def save_bytes(self, key: str, content: bytes) -> SavedFile:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "content"
            await asyncio.to_thread(path.write_bytes, content)
            return await self._storage.save_path(self._prefix + key, path)

    # 判断本模块正式文件是否存在。
    async def exists(self, key: str) -> bool:
        return await self._storage.exists(self._full(key))

    # 把临时上传保存到正式存储，成功后删除临时文件；返回带模块前缀的完整键。
    async def adopt(self, temp_id: str, key: str) -> SavedFile:
        path, _ = await self._uploads.find(temp_id)
        saved = await self._storage.save_path(self._prefix + key, path)
        await self._uploads.discard(temp_id)
        return saved

    # 读取完整内容，超过 max_bytes 时报错。
    async def read(self, key: str, max_bytes: int) -> bytes:
        parts, size = [], 0
        async for chunk in self._storage.open(self._full(key)):
            size += len(chunk)
            if size > max_bytes:
                raise FileTooLarge(f"文件超过读取上限 {max_bytes} 字节")
            parts.append(chunk)
        return b"".join(parts)

    # 按块读取内容。
    def open(self, key: str) -> AsyncIterator[bytes]:
        return self._storage.open(self._full(key))

    # 删除文件。
    async def delete(self, key: str) -> None:
        await self._storage.delete(self._full(key))

    # 清理超过指定秒数仍未被保存的临时上传。
    async def clean_uploads(self, older_than: float) -> int:
        return await self._uploads.clean(older_than)

    # 逐项列出本模块已保存的对象，供文件记录检查。
    def list_objects(self) -> AsyncIterator[StoredObject]:
        return self._storage.list_objects(self._prefix)

    # 补全带模块前缀的键；已经带前缀的键保持不变。
    def _full(self, key: str) -> str:
        return key if key.startswith(self._prefix) else self._prefix + key


# 即使文件在信息检查后变大，也只读取上限加一字节。
def read_bounded(path: Path, maximum: int) -> bytes:
    with path.open("rb") as source:
        content = source.read(maximum + 1)
    if len(content) > maximum:
        raise FileTooLarge(f"文件超过读取上限 {maximum} 字节")
    return content
