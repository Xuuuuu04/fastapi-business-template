"""
从 HTTP 入口验证登录会话（R-05 至 R-07）及相关用户管理规则。
"""

import asyncio

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from service.user_access.data import TokenCheck
from service.user_access.public import purge_sessions
from service.user_access.store.sessions import SessionStore, digest_of
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
    body = {"org_code": "north", "username": "alice", "password": password}
    reply = client.post(LOGIN, json=body)
    assert reply.status_code == 200, reply.text
    return dict(reply.json())


# 用访问令牌组成请求头。
def bearer(tokens: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


# R-05：每次刷新换新刷新令牌；旧令牌再次提交时，连同新令牌一起作废。
@pytest.mark.rule_case("user_access.R-05-C01")
@pytest.mark.rule_case("user_access.R-05-C02")
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


# 两次真实只读检查都完成后，允许第一个 HTTP 请求提交，再允许第二个进入真实写事务。
async def refresh_after_both_checks(
    client: TestClient, token: str, monkeypatch: pytest.MonkeyPatch
) -> list[httpx.Response]:
    original = SessionStore.check_refresh
    both_checked, first_committed = asyncio.Event(), asyncio.Event()
    statuses: list[str] = []

    # 保留真实查询，只控制读取完成后的顺序，不替代 Runtime 或保存操作。
    async def checked(store: SessionStore, value: str) -> TokenCheck:
        result = await original(store, value)
        statuses.append(result.status)
        position = len(statuses)
        if position == 2:
            both_checked.set()
        await asyncio.wait_for(both_checked.wait(), timeout=5)
        if position == 2:
            await asyncio.wait_for(first_committed.wait(), timeout=5)
        return result

    monkeypatch.setattr(SessionStore, "check_refresh", checked)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=client.app), base_url="http://testserver"
    ) as http:
        # 第一个响应只有在 Runtime 的写事务提交后才返回。
        async def request() -> httpx.Response:
            reply = await http.post(REFRESH, json={"refresh_token": token})
            first_committed.set()
            return reply

        replies = await asyncio.wait_for(asyncio.gather(request(), request()), timeout=10)
    assert statuses == ["active", "active"]
    return replies


# R-05：两个请求先读到 active，竞争失败仍需提交整组作废，首次返回的新令牌也不能刷新。
@pytest.mark.rule_case("user_access.R-05-C05")
def test_concurrent_refresh_reuse_revokes_family(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepare(client)
    initial = sign_in(client)
    other_login = sign_in(client)
    with monkeypatch.context() as patch:
        replies = client.portal.call(
            refresh_after_both_checks, client, initial["refresh_token"], patch
        )
    assert sorted(reply.status_code for reply in replies) == [200, 401]
    renewed = next(reply.json() for reply in replies if reply.status_code == 200)
    rejected = next(reply for reply in replies if reply.status_code == 401)
    assert rejected.json()["code"] == "refresh_rejected"
    database = client.app.state.services.database
    digests = [digest_of(str(initial["refresh_token"])), digest_of(renewed["refresh_token"])]

    # 直接读取真实保存结果，确认旧令牌和新令牌均已作废，而不是只检查一次 HTTP 拒绝。
    async def revoked_family() -> list[bool]:
        async with database.read() as connection:
            rows = await connection.execute(
                select(refresh_tokens.c.revoked_at).where(
                    refresh_tokens.c.token_sha256.in_(digests)
                )
            )
            return [value is not None for value in rows.scalars()]

    assert client.portal.call(revoked_family) == [True, True]
    assert client.post(REFRESH, json={"refresh_token": renewed["refresh_token"]}).status_code == 401
    other = client.post(REFRESH, json={"refresh_token": other_login["refresh_token"]})
    assert other.status_code == 200


# R-05：检查后发生过期或退出作废时，保存拒绝刷新，不额外作废或签发令牌。
@pytest.mark.parametrize(
    "field",
    [
        pytest.param("expires_at", marks=pytest.mark.rule_case("user_access.R-05-C06")),
        pytest.param("revoked_at", marks=pytest.mark.rule_case("user_access.R-05-C07")),
    ],
)
def test_refresh_rechecks_expiry_and_revocation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    prepare(client)
    token = str(sign_in(client)["refresh_token"])
    database = client.app.state.services.database
    original = SessionStore.check_refresh

    # 真实检查已读到 active 后，用独立写事务模拟过期或退出先完成。
    async def changed_before_save(store: SessionStore, value: str) -> TokenCheck:
        check = await original(store, value)
        assert check.status == "active"
        async with database.write() as connection:
            await connection.execute(
                update(refresh_tokens)
                .where(refresh_tokens.c.token_sha256 == digest_of(value))
                .values({field: 1.0})
            )
        return check

    with monkeypatch.context() as patch:
        patch.setattr(SessionStore, "check_refresh", changed_before_save)
        reply = client.post(REFRESH, json={"refresh_token": token})
    assert reply.status_code == 401 and reply.json()["code"] == "refresh_rejected"

    # 写事务只保留原记录与原作废状态；过期不能被误判为重复使用。
    async def saved_state() -> list[tuple[object, object]]:
        async with database.read() as connection:
            rows = await connection.execute(
                select(refresh_tokens.c.used_at, refresh_tokens.c.revoked_at)
            )
            return [tuple(row) for row in rows]

    assert client.portal.call(saved_state) == [(None, 1.0 if field == "revoked_at" else None)]


# R-02、R-05：停用用户后刷新立即失败；角色变化在下一次刷新时写进新令牌。
@pytest.mark.rule_case("user_access.R-05-C03")
def test_disable_and_role_change(client: TestClient) -> None:
    viewer, manager, user_id = prepare(client)
    tokens = sign_in(client)
    url = "/api/v1/access/users?org_id=north"
    assert client.get(url, headers=bearer(tokens)).status_code == 403
    change = {"org_id": "north", "user_id": user_id, "role_id": manager, "active": True}
    assert client.put("/api/v1/access/users", json=change, headers=KEY).status_code == 200
    tokens = client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]}).json()
    assert client.get(url, headers=bearer(tokens)).status_code == 200
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
    history = client.get("/api/system/changes?table=user_access_users", headers=KEY).json()
    [change] = [item for item in history["items"] if item["field"] == "password_hash"]
    assert change["before"] == change["after"] == "（已隐藏）"


# R-05、R-07：退出登录后刷新令牌失效；系统任务删除作废超过一天的记录。
@pytest.mark.rule_case("user_access.R-05-C04")
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


# R-03：同一账号的失败次数跨来源地址累计：换地址也不能继续猜密码，达到上限后正确密码也要等窗口结束。
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


# R-04：用户列表按编号从小到大，按位置续读：每页返回下一页的位置，最后一页位置为空；位置写错时拒绝。
def test_user_list_pages(client: TestClient) -> None:
    role, _, first_user = prepare(client)
    body = {"org_id": "north", "password": "correct-password", "role_id": role}
    for name in ("bob", "carol"):
        client.post("/api/v1/access/users", json={**body, "username": name}, headers=KEY)
    url = "/api/v1/access/users?org_id=north&limit=2"
    first = client.get(url, headers=KEY).json()
    assert [item["username"] for item in first["items"]] == ["alice", "bob"]
    assert first["items"][0]["id"] == first_user and first["next_after"]
    second = client.get(f"{url}&after={first['next_after']}", headers=KEY).json()
    assert [item["username"] for item in second["items"]] == ["carol"]
    assert second["next_after"] == ""
    assert client.get(f"{url}&after=abc", headers=KEY).status_code == 422
