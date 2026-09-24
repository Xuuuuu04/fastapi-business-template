"""
从 HTTP 入口验证上传、隔离、下载、删除和清理。
"""

import os
import time
from pathlib import Path

from fastapi.testclient import TestClient

from service.file_library.public import clean_files
from shared.access.caller import SYSTEM
from shared.public import Nothing
from tests.testing_app import KEY


# 文件保存后可查询和下载，跨组织不能下载，删除后由系统清理。
def test_file_lifecycle(client: TestClient) -> None:
    uploaded = client.post(
        "/api/v1/files/north",
        files={"upload": ("report.txt", b"hello north", "text/plain")},
        headers=KEY,
    )
    assert uploaded.status_code == 200, uploaded.text
    info = uploaded.json()
    assert info["name"] == "report.txt"
    assert info["size"] == len(b"hello north")
    file_id = info["id"]
    listing = client.get("/api/v1/files/north", headers=KEY)
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["items"]] == [file_id]
    found = client.get(f"/api/v1/files/north/{file_id}/info", headers=KEY)
    assert found.status_code == 200
    assert found.json()["sha256"] == info["sha256"]
    content = client.get(f"/api/v1/files/north/{file_id}/download", headers=KEY)
    assert content.status_code == 200
    assert content.content == b"hello north"
    assert client.get(f"/api/v1/files/south/{file_id}/download", headers=KEY).status_code == 404
    assert client.delete(f"/api/v1/files/north/{file_id}", headers=KEY).status_code == 204
    assert client.get(f"/api/v1/files/north/{file_id}/info", headers=KEY).status_code == 404

    orphan = Path(client.app.state.settings.file_root) / "file_library/north/orphan"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_bytes(b"left after unknown commit")
    os.utime(orphan, (time.time() - 7200, time.time() - 7200))

    # 在应用事件循环内执行系统清理操作。
    async def clean() -> tuple[int, int]:
        result = await client.app.state.services.runtime.run(clean_files, Nothing(), caller=SYSTEM)
        return result.removed, result.orphan_removed

    assert client.portal.call(clean) == (1, 1)
    assert not orphan.exists()
    assert client.get("/api/v1/files/north", headers=KEY).json()["items"] == []


# 不允许的文件类型和匿名上传都被拒绝。
def test_reject_file_type_and_anonymous_write(client: TestClient) -> None:
    assert (
        client.post(
            "/api/v1/files/north", files={"upload": ("script.exe", b"x")}, headers=KEY
        ).status_code
        == 422
    )
    assert (
        client.post("/api/v1/files/north", files={"upload": ("report.txt", b"x")}).status_code
        == 401
    )


# R-02：文件列表分页返回，带总数，按保存时间从新到旧；每页超过 100 条时拒绝。
def test_file_list_pages(client: TestClient) -> None:
    for number in range(3):
        reply = client.post(
            "/api/v1/files/north",
            files={"upload": (f"page-{number}.txt", b"x", "text/plain")},
            headers=KEY,
        )
        assert reply.status_code == 200, reply.text
    first = client.get("/api/v1/files/north?limit=2", headers=KEY).json()
    second = client.get("/api/v1/files/north?offset=2&limit=2", headers=KEY).json()
    assert first["total"] == 3 and len(first["items"]) == 2
    assert len(second["items"]) == 1
    names = [item["name"] for item in first["items"] + second["items"]]
    assert sorted(names) == ["page-0.txt", "page-1.txt", "page-2.txt"]
    assert client.get("/api/v1/files/north?limit=101", headers=KEY).status_code == 422
