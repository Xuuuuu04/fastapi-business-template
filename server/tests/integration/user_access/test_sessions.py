"""
从 HTTP 入口验证登录会话（R-05 至 R-07）：刷新令牌轮换、重复使用时整组作废、
停用用户与修改密码后立即失效、角色变化在刷新时生效、退出登录和清理过期记录。
"""

from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from service.user_access.public import purge_sessions
from service.user_access.store.tables import refresh_tokens
from shared.access.caller import SYSTEM
from shared.public import Nothing
from tests.testing_app import KEY

LOGIN = "/api/v1/access/login"
REFRESH = "/api/v1/access/refresh"


# 建立北区、两个角色和用户 alice，返回两个角色编号和用户编号。
def prepare(client: TestClient) -> tuple[int, int, int]:
    client.post("/api/v1/access/orgs", json={"code": "north", "name": "北区"}, headers=KEY)
    roles = [
        client.post(
            "/api/v1/access/roles",
            json={"org_id": "north", "name": name, "permissions": permissions},
            headers=KEY,
        ).json()["id"]
        for name, permissions in (
            ("viewer", ["file_library.read"]),
            ("manager", ["user_access.manage"]),
        )
    ]
    user = client.post(
        "/api/v1/access/users",
        json={
            "org_id": "north",
            "username": "alice",
            "password": "correct-password",
            "role_id": roles[0],
        },
        headers=KEY,
    ).json()
    return roles[0], roles[1], user["id"]


# 用 alice 的密码登录，返回令牌响应。
def sign_in(client: TestClient, password: str = "correct-password") -> dict[str, object]:
    reply = client.post(
        LOGIN, json={"org_code": "north", "username": "alice", "password": password}
    )
    assert reply.status_code == 200, reply.text
    return dict(reply.json())


# 用访问令牌组成请求头。
def bearer(tokens: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


# R-05：每次刷新换新刷新令牌；旧令牌再次提交时，连同新令牌一起作废。
def test_refresh_rotates_and_detects_reuse(client: TestClient) -> None:
    prepare(client)
    first = sign_in(client)
    assert first["token_type"] == "Bearer" and first["expires_in"] == 15 * 60
    assert "correct-password" not in str(first)
    second = client.post(REFRESH, json={"refresh_token": first["refresh_token"]})
    assert second.status_code == 200, second.text
    renewed = second.json()
    assert renewed["refresh_token"] != first["refresh_token"]
    assert client.get("/api/v1/files/north", headers=bearer(renewed)).status_code == 200

    reused = client.post(REFRESH, json={"refresh_token": first["refresh_token"]})
    assert reused.status_code == 401 and reused.json()["code"] == "refresh_rejected"
    stolen = client.post(REFRESH, json={"refresh_token": renewed["refresh_token"]})
    assert stolen.status_code == 401
    report = client.get(f"/api/system/runs/{reused.headers['x-run-id']}/report", headers=KEY)
    assert "整组登录会话已作废" in report.text
    assert first["refresh_token"] not in report.text


# R-02、R-05：停用用户后刷新立即失败；角色变化在下一次刷新时写进新令牌。
def test_disable_and_role_change(client: TestClient) -> None:
    viewer, manager, user_id = prepare(client)
    tokens = sign_in(client)
    assert (
        client.get("/api/v1/access/users?org_id=north", headers=bearer(tokens)).status_code == 403
    )
    change = {"org_id": "north", "user_id": user_id, "role_id": manager, "active": True}
    assert client.put("/api/v1/access/users", json=change, headers=KEY).status_code == 200
    tokens = client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]}).json()
    assert (
        client.get("/api/v1/access/users?org_id=north", headers=bearer(tokens)).status_code == 200
    )

    change |= {"role_id": viewer, "active": False}
    assert client.put("/api/v1/access/users", json=change, headers=KEY).status_code == 200
    refused = client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]})
    assert refused.status_code == 401


# R-06：原密码错误时拒绝；改成功后旧刷新令牌失效，只能用新密码登录。
def test_change_password(client: TestClient) -> None:
    prepare(client)
    tokens = sign_in(client)
    url = "/api/v1/access/password"
    wrong = {"old_password": "wrong-password", "new_password": "new-password-1"}
    assert client.post(url, json=wrong).status_code == 401
    assert client.post(url, json=wrong, headers=KEY).status_code == 403
    mismatch = client.post(url, json=wrong, headers=bearer(tokens))
    assert mismatch.status_code == 422 and mismatch.json()["code"] == "password_mismatch"
    right = {"old_password": "correct-password", "new_password": "new-password-1"}
    assert client.post(url, json=right, headers=bearer(tokens)).status_code == 204
    assert client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    old = client.post(
        LOGIN, json={"org_code": "north", "username": "alice", "password": "correct-password"}
    )
    assert old.status_code == 401
    sign_in(client, "new-password-1")


# R-05、R-07：退出登录后刷新令牌失效；系统任务删除作废超过一天的记录。
def test_logout_and_purge(client: TestClient) -> None:
    prepare(client)
    tokens = sign_in(client)
    body = {"refresh_token": tokens["refresh_token"]}
    assert client.post("/api/v1/access/logout", json=body).status_code == 204
    assert client.post("/api/v1/access/logout", json=body).status_code == 204
    assert client.post(REFRESH, json=body).status_code == 401
    sign_in(client)
    database = client.app.state.services.database
    runtime = client.app.state.services.runtime

    # 把已作废的记录改成两天前作废，再运行清理，只删除这一条。
    async def purge() -> tuple[int, int]:
        async with database.write() as connection:
            await connection.execute(
                update(refresh_tokens)
                .where(refresh_tokens.c.revoked_at.is_not(None))
                .values(revoked_at=1.0)
            )
        result = await runtime.run(purge_sessions, Nothing(), caller=SYSTEM)
        async with database.read() as connection:
            left = await connection.scalar(select(func.count()).select_from(refresh_tokens))
        return result.removed, int(left)

    assert client.portal.call(purge) == (1, 1)


# 同一账号的失败次数跨来源地址累计：换地址也不能继续猜密码，达到上限后正确密码也要等窗口结束。
def test_account_failures_are_limited_across_sources(client: TestClient) -> None:
    prepare(client)
    app = client.app
    app.state.settings = app.state.settings.model_copy(  # type: ignore[attr-defined]
        update={"login_failure_limit": 100, "login_account_failure_limit": 3}
    )
    wrong = {"org_code": "north", "username": "alice", "password": "wrong-password"}
    replies = []
    for number in range(4):
        with TestClient(app, client=(f"10.0.0.{number}", 5000)) as other:
            replies.append(other.post(LOGIN, json=wrong).status_code)
    assert replies == [401, 401, 401, 429]
    with TestClient(app, client=("10.0.0.9", 5000)) as other:
        right = {**wrong, "password": "correct-password"}
        assert other.post(LOGIN, json=right).status_code == 429


# R-04：用户列表分页返回，带总数，按编号从小到大。
def test_user_list_pages(client: TestClient) -> None:
    role, _, first_user = prepare(client)
    body = {"org_id": "north", "password": "correct-password", "role_id": role}
    for name in ("bob", "carol"):
        client.post("/api/v1/access/users", json={**body, "username": name}, headers=KEY)
    page = client.get("/api/v1/access/users?org_id=north&offset=1&limit=1", headers=KEY).json()
    assert page["total"] == 3 and page["offset"] == 1 and page["limit"] == 1
    assert [item["username"] for item in page["items"]] == ["bob"]
    assert page["items"][0]["id"] > first_user
