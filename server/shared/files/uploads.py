import hashlib
import json
import mimetypes
import re
import secrets
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
from pathlib import Path, PurePath

import anyio

from shared.errors.framework import FileTooLarge, FileTypeNotAllowed, StepRuleBroken
from shared.timing.current import now as business_now

TEMP_ID = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class TempUpload:
    temp_id: str
    name: str
    size: int
    sha256: str
    content_type: str


class UploadArea:
    def __init__(self, root: Path, max_bytes: int, suffixes: list[str]) -> None:
        self.root = root
        self.max_bytes = max_bytes
        self.suffixes = {suffix.lower() for suffix in suffixes}

    async def receive(self, name: str, chunks: AsyncIterator[bytes]) -> TempUpload:
        clean = PurePath(name.replace("\\", "/")).name[:200] or "file"
        suffix = PurePath(clean).suffix.lower()
        if suffix not in self.suffixes:
            raise FileTypeNotAllowed(
                f"不允许上传 {suffix or '没有扩展名'} 文件", fields={"file": "文件类型不允许"}
            )
        temp_id = secrets.token_hex(16)
        await anyio.Path(self.root).mkdir(parents=True, exist_ok=True)
        digest, size = hashlib.sha256(), 0
        try:
            async with await anyio.open_file(self.root / temp_id, "wb") as target:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise FileTooLarge(
                            f"文件超过 {self.max_bytes // 1_000_000} MB",
                            fields={"file": "文件太大"},
                        )
                    digest.update(chunk)
                    await target.write(chunk)
        except BaseException:
            await self.discard(temp_id)
            raise
        content_type = mimetypes.guess_type(clean)[0] or "application/octet-stream"
        upload = TempUpload(temp_id, clean, size, digest.hexdigest(), content_type)
        await anyio.Path(self.root / f"{temp_id}.json").write_text(
            json.dumps(asdict(upload), ensure_ascii=False)
        )
        return upload

    async def find(self, temp_id: str) -> tuple[Path, TempUpload]:
        if not TEMP_ID.match(temp_id):
            raise StepRuleBroken("临时文件编号格式不正确")
        info = anyio.Path(self.root / f"{temp_id}.json")
        if not await info.is_file():
            raise FileTypeNotAllowed("临时文件不存在或已过期，请重新上传")
        upload = TempUpload(**json.loads(await info.read_text()))
        return self.root / temp_id, upload

    async def discard(self, temp_id: str) -> None:
        for name in (temp_id, f"{temp_id}.json"):
            await anyio.Path(self.root / name).unlink(missing_ok=True)

    async def clean(self, older_than: float) -> int:
        folder = anyio.Path(self.root)
        if not await folder.is_dir():
            return 0
        cutoff, count = business_now() - older_than, 0
        async for path in folder.iterdir():
            if (await path.stat()).st_mtime < cutoff:
                await path.unlink(missing_ok=True)
                count += 1
        return count
