from pathlib import Path

import pytest

from shared.operations.backup import check_tools

pytestmark = pytest.mark.anyio


class Server:
    async def scalar(self, _query: object) -> str:
        return "160004"


def fake_tools(folder: Path, version: str) -> None:
    for tool in ("pg_dump", "pg_restore"):
        path = folder / tool
        path.write_text(f"#!/bin/sh\necho '{tool} (PostgreSQL) {version}'\n")
        path.chmod(0o755)


async def test_backup_tools_must_match_server_major(tmp_path: Path) -> None:
    fake_tools(tmp_path, "17.2")
    with pytest.raises(RuntimeError, match="主版本17与数据库主版本16不一致"):
        await check_tools(Server(), str(tmp_path))
    fake_tools(tmp_path, "16.4")
    await check_tools(Server(), str(tmp_path))
    with pytest.raises(RuntimeError, match="找不到pg_dump"):
        await check_tools(Server(), str(tmp_path / "missing"))
