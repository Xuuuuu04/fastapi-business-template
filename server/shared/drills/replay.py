import hashlib
from pathlib import Path
from typing import Any

import httpx2

from shared.errors.framework import InvalidInput


class Replay(httpx2.AsyncBaseTransport):
    def __init__(self, name: str, entries: list[dict[str, Any]], root: Path) -> None:
        self.name, self.entries, self.root = name, entries, root.resolve()
        self.used: list[dict[str, Any]] = []

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


def transports(manifest: dict[str, Any], root: Path, names: set[str]) -> dict[str, Replay]:
    return {name: Replay(name, manifest.get(name, []), root) for name in names}


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
