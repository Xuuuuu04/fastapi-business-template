"""
从 HTTP 入口验证组织、角色、用户管理和令牌登录。
"""

from fastapi.testclient import TestClient

from tests.testing_app import KEY


# 创建北区组织、角色和用户，返回后续修改需要的编号。
def create_north_user(client: TestClient) -> tuple[int, int]:
    created = client.post(
        "/api/v1/access/orgs", json={"code": "north", "name": " 北区 "}, headers=KEY
    )
    assert created.status_code == 200, created.text
    assert created.json() == {"code": "north", "name": "北区"}
    assert client.get("/api/v1/access/orgs", headers=KEY).json()["items"] == [created.json()]
    assert (
        client.post(
            "/api/v1/access/orgs", json={"code": "north", "name": "重复"}, headers=KEY
        ).status_code
        == 409
    )

    role = client.post(
        "/api/v1/access/roles",
        json={"org_id": "north", "name": "viewer", "permissions": ["file_library.read"]},
        headers=KEY,
    )
    assert role.status_code == 200, role.text
    role_id = role.json()["id"]
    assert len(client.get("/api/v1/access/roles?org_id=north", headers=KEY).json()["items"]) == 1

    user = client.post(
        "/api/v1/access/users",
        json={
            "org_id": "north",
            "username": "alice",
            "password": "correct-password",
            "role_id": role_id,
        },
        headers=KEY,
    )
    assert user.status_code == 200, user.text
    user_id = user.json()["id"]
    users = client.get("/api/v1/access/users?org_id=north", headers=KEY)
    assert users.status_code == 200
    assert len(users.json()["items"]) == 1
    assert "password" not in users.text
    audit = client.get("/api/system/audit", headers=KEY)
    assert audit.status_code == 200
    assert any(item["contract"] == "user_access.create_org" for item in audit.json()["items"])
    assert "correct-password" not in audit.text
    return role_id, user_id


# 正确密码可登录，错误密码和停用状态都会拒绝登录。
def test_manage_users_and_login(client: TestClient) -> None:
    role_id, user_id = create_north_user(client)
    login = client.post(
        "/api/v1/access/login",
        json={"org_code": "north", "username": "alice", "password": "correct-password"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["token"]
    bearer = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/access/users?org_id=north", headers=bearer).status_code == 403
    assert client.get("/api/v1/files/north", headers=bearer).status_code == 200
    invalid = {"Authorization": f"Bearer {token}broken"}
    assert client.get("/api/v1/files/north", headers=invalid).status_code == 401
    assert (
        client.post(
            "/api/v1/access/login",
            json={"org_code": "north", "username": "alice", "password": "wrong-password"},
        ).status_code
        == 401
    )

    changed = client.put(
        "/api/v1/access/users",
        json={"org_id": "north", "user_id": user_id, "role_id": role_id, "active": False},
        headers=KEY,
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["active"] is False
    assert (
        client.post(
            "/api/v1/access/login",
            json={"org_code": "north", "username": "alice", "password": "correct-password"},
        ).status_code
        == 401
    )


# 用全权限密钥建立北区和南区，并创建北区管理员，返回管理员的令牌请求头。
def north_manager(client: TestClient) -> dict[str, str]:
    for code in ("north", "south"):
        assert (
            client.post(
                "/api/v1/access/orgs", json={"code": code, "name": code}, headers=KEY
            ).status_code
            == 200
        )
    role = client.post(
        "/api/v1/access/roles",
        json={"org_id": "north", "name": "manager", "permissions": ["user_access.manage"]},
        headers=KEY,
    ).json()
    client.post(
        "/api/v1/access/users",
        json={
            "org_id": "north",
            "username": "manager",
            "password": "correct-password",
            "role_id": role["id"],
        },
        headers=KEY,
    )
    token = client.post(
        "/api/v1/access/login",
        json={"org_code": "north", "username": "manager", "password": "correct-password"},
    ).json()["token"]
    return {"Authorization": f"Bearer {token}"}


# 组织管理员只能查看自己组织的数据。
def test_org_scope_rejects_other_org(client: TestClient) -> None:
    bearer = north_manager(client)
    assert client.get("/api/v1/access/users?org_id=south", headers=bearer).status_code == 403
    assert client.get("/api/v1/access/orgs", headers=bearer).json()["items"] == [
        {"code": "north", "name": "north"}
    ]


# R-02：角色权限不能超出授予者自己的权限，跨组织的系统权限不能放进组织角色。
def test_roles_cannot_raise_permissions(client: TestClient) -> None:
    bearer = north_manager(client)
    for permissions in (["system.diagnostics"], ["user_access.manage", "product_catalog.write"]):
        escalated = client.post(
            "/api/v1/access/roles",
            json={"org_id": "north", "name": "raised", "permissions": permissions},
            headers=bearer,
        )
        assert escalated.status_code == 403, escalated.text
    platform = client.post(
        "/api/v1/access/roles",
        json={"org_id": "north", "name": "operator", "permissions": ["system.jobs"]},
        headers=KEY,
    )
    assert platform.status_code == 403, platform.text
    own = client.post(
        "/api/v1/access/roles",
        json={"org_id": "north", "name": "helper", "permissions": ["user_access.manage"]},
        headers=bearer,
    )
    assert own.status_code == 200, own.text
