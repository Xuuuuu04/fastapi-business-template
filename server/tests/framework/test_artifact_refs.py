"""
原件冻结、并发同内容、组织边界和有界窗口，验证批次不反复加载完整文件。
"""

import asyncio
import io
from pathlib import Path

import pytest

from shared.access.caller import Caller
from shared.errors.framework import FileTooLarge, StepRuleBroken
from shared.files.artifacts import ArtifactRef
from shared.files.gate import ModuleFiles
from shared.files.storage import LocalFiles, S3Files
from shared.files.uploads import UploadArea

pytestmark = pytest.mark.anyio


# 上传分块来自合成内存，实际写入、冻结和范围读取使用正式实现。
async def upload(area: UploadArea, content: bytes) -> str:
    # 控制每块大小，不一次交给上传器整个大原件。
    async def chunks():
        for start in range(0, len(content), 65536):
            yield content[start : start + 65536]

    return (await area.receive("source.txt", chunks())).temp_id


# 同内容并发提交只生成相同引用，窗口读取不调用全文读取接口。
async def test_freeze_and_bounded_windows(tmp_path: Path, monkeypatch) -> None:
    area = UploadArea(tmp_path / "uploads", 8_000_000, [".txt"])
    storage = LocalFiles(tmp_path / "files")
    gate = ModuleFiles(storage, area, "batch_reads", Caller("user", "user", "用户", org_id="a"))
    content = b"header\n" + b"0123456789\n" * 100_000
    first, second = await asyncio.gather(upload(area, content), upload(area, content))
    refs = await asyncio.gather(gate.freeze(first), gate.freeze(second))
    assert refs[0] == refs[1] and refs[0].size == len(content)

    # 原件已经冻结，任何批次重读全文都是错误。
    def no_full_read(key: str):
        raise AssertionError("窗口批次不能重新加载全文")

    monkeypatch.setattr(storage, "open", no_full_read)
    assert await gate.read_window(refs[0], 100_000, 512) == content[100_000:100_512]
    assert await gate.read_window(refs[0], len(content) - 20, 20) == content[-20:]
    with pytest.raises(FileTooLarge):
        await gate.read_window(refs[0], 0, 1001, max_bytes=1000)
    with pytest.raises(StepRuleBroken, match="不允许覆盖"):
        await gate.save_bytes(refs[0].key, b"changed")
    foreign = ModuleFiles(storage, area, "batch_reads", Caller("user", "user", "用户", org_id="b"))
    with pytest.raises(StepRuleBroken, match="不属于"):
        await foreign.read_window(refs[0], 0, 10)


# 原件被外部修改后，完整流读取不能继续被当作已经验证的原件。
async def test_stream_detects_changed_content(tmp_path: Path) -> None:
    area = UploadArea(tmp_path / "uploads", 1000, [".txt"])
    storage = LocalFiles(tmp_path / "files")
    gate = ModuleFiles(storage, area, "batch_reads")
    ref = await gate.freeze(await upload(area, b"original"))
    assert b"".join([chunk async for chunk in gate.open_artifact(ref)]) == b"original"
    (storage.root / ref.key).write_bytes(b"changed!")
    with pytest.raises(StepRuleBroken, match="不一致"):
        _ = [chunk async for chunk in gate.open_artifact(ref)]


# S3适配器确认ContentRange，不能把忽略Range后返回的头部当作指定窗口。
async def test_s3_range_requires_matching_headers() -> None:
    requests = []

    # 模拟S3兼容服务，但保留真实范围请求与响应检查。
    class Client:
        # 第一轮正确响应，第二轮故意忽略范围。
        def get_object(self, **kwargs):
            requests.append(kwargs)
            return {
                "Body": io.BytesIO(b"range"),
                "ContentLength": 5,
                "ContentRange": "bytes 10-14/100" if len(requests) == 1 else "bytes 0-4/100",
            }

    storage = object.__new__(S3Files)
    storage.bucket, storage.client = "synthetic", Client()
    ref = ArtifactRef(key="batch_reads/artifacts/x", size=100, sha256="a" * 64)
    assert b"".join([chunk async for chunk in storage.open_range(ref.key, 10, 5)]) == b"range"
    assert requests[0]["Range"] == "bytes=10-14"
    with pytest.raises(StepRuleBroken, match="有界范围"):
        _ = [chunk async for chunk in storage.open_range(ref.key, 10, 5)]
