"""
原件回放传输：只从清单指定的本地原始文件返回响应，未覆盖请求失败，不访问真实系统。
"""

import hashlib
from pathlib import Path
from typing import Any

import httpx2

from shared.errors.framework import InvalidInput


# 按外部系统/方法/路径选择原件，保持原始字节和响应类型，不重新生成业务结果。
class Replay(httpx2.AsyncBaseTransport):
    # 清单只接受本地目录内原件，记录被实际消费的覆盖信息。
    def __init__(self, name: str, entries: list[dict[str, Any]], root: Path) -> None:
        self.name, self.entries, self.root = name, entries, root.resolve()
        self.used: list[dict[str, Any]] = []

    # 缺失清单明确失败，写外部系统也仅回放已确认响应。
    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        params = dict(request.url.params)
        match = next(
            (item for item in self.entries if matches(item, request, params)),
            None,
        )
        if match is None:
            raise InvalidInput(f"回放未覆盖{self.name} {request.method} {request.url.path}")
        path = (self.root / match["file"]).resolve()
        if not path.is_relative_to(self.root) or path.is_symlink() or not path.is_file():
            raise InvalidInput("回放原件路径超出清单目录或不存在")
        import asyncio

        content = await asyncio.to_thread(path.read_bytes)
        digest = hashlib.sha256(content).hexdigest()
        if match.get("sha256") and match["sha256"] != digest:
            raise InvalidInput("回放原件摘要不符")
        self.used.append(
            dict(
                remote=self.name,
                endpoint=request.extensions.get("endpoint", ""),
                method=request.method,
                path=request.url.path,
                file=match["file"],
                sha256=digest,
                bytes=len(content),
            )
        )
        return httpx2.Response(
            match.get("status", 200),
            content=content,
            headers=match.get("headers", {"content-type": "application/json"}),
            request=request,
        )


# 清单只加载声明，不读取业务原件正文；未配置的外部系统得到拒绝回放。
def transports(manifest: dict[str, Any], root: Path, names: set[str]) -> dict[str, Replay]:
    return {name: Replay(name, manifest.get(name, []), root) for name in names}


# 名称回放仍核对显式提供的方法/路径/查询；旧清单保留原精确匹配。
def matches(item: dict[str, Any], request: httpx2.Request, params: dict[str, str]) -> bool:
    if "endpoint" in item:
        if not item["endpoint"] or item["endpoint"] != request.extensions.get("endpoint"):
            return False
        return (
            item.get("method", request.method).upper() == request.method
            and item.get("path", request.url.path) == request.url.path
            and ("params" not in item or item["params"] == params)
        )
    return (
        item["method"].upper() == request.method
        and item["path"] == request.url.path
        and item.get("params", {}) == params
    )
