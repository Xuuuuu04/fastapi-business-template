"""
从 HTTP 入口验证组织、角色、用户管理和令牌登录。
"""

import pytest
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


# R-03：正确密码可登录，错误密码和停用状态都会拒绝登录。
def test_manage_users_and_login(client: TestClient) -> None:
    role_id, user_id = create_north_user(client)
    login = client.post(
        "/api/v1/access/login",
        json={"org_code": "north", "username": "alice", "password": "correct-password"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
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
    ).json()["access_token"]
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


# 在 HTTP 中用指定角色创建账号，检查成功后返回公开用户信息。
def assign_new_user(client: TestClient, role: int, headers: dict[str, str]) -> dict[str, object]:
    reply = client.post(
        "/api/v1/access/users",
        json={
            "org_id": "north",
            "username": "controlled",
            "password": "correct-password",
            "role_id": role,
        },
        headers=headers,
    )
    assert reply.status_code == 200, reply.text
    return dict(reply.json())


# R-02：创建、调整用户都不能分配系统预先创建的、超出自己权限的角色。
@pytest.mark.parametrize("operation", ["create", "change"])
def test_existing_role_assignment_cannot_raise_permissions(
    client: TestClient, operation: str
) -> None:
    manager = north_manager(client)
    elevated = client.post(
        "/api/v1/access/roles",
        json={"org_id": "north", "name": "writer", "permissions": ["file_library.write"]},
        headers=KEY,
    ).json()["id"]
    own = client.get("/api/v1/access/roles?org_id=north", headers=manager).json()["items"][0]["id"]
    body = {"org_id": "north", "role_id": elevated}
    if operation == "create":
        body |= {"username": "controlled", "password": "correct-password"}
        reply = client.post("/api/v1/access/users", json=body, headers=manager)
    else:
        controlled = assign_new_user(client, own, manager)
        body |= {"user_id": controlled["id"], "active": False}
        reply = client.put("/api/v1/access/users", json=body, headers=manager)
    assert reply.status_code == 403, reply.text
    assert reply.json()["code"] == "not_allowed"
    saved = client.get("/api/v1/access/users?org_id=north", headers=KEY).json()["items"]
    controlled_users = [user for user in saved if user["username"] == "controlled"]
    if operation == "create":
        assert controlled_users == []
    else:
        assert controlled_users == [controlled]


# R-02：正常已有角色可分配，系统全权限仍可管理；不存在与其他组织的角色明确拒绝。
def test_existing_role_assignment_normal_and_missing(client: TestClient) -> None:
    manager = north_manager(client)
    roles = "/api/v1/access/roles"
    own = client.post(
        roles,
        json={"org_id": "north", "name": "helper", "permissions": ["user_access.manage"]},
        headers=manager,
    ).json()["id"]
    writer = client.post(
        roles,
        json={"org_id": "north", "name": "writer", "permissions": ["file_library.write"]},
        headers=KEY,
    ).json()["id"]
    foreign = client.post(
        roles,
        json={"org_id": "south", "name": "helper", "permissions": ["user_access.manage"]},
        headers=KEY,
    ).json()["id"]
    user = assign_new_user(client, own, manager)
    change = {"org_id": "north", "user_id": user["id"], "role_id": writer, "active": True}
    assert client.put("/api/v1/access/users", json=change, headers=KEY).status_code == 200
    change["role_id"] = own
    assert client.put("/api/v1/access/users", json=change, headers=manager).status_code == 200
    for missing in (foreign, 999999):
        change["role_id"] = missing
        refused = client.put("/api/v1/access/users", json=change, headers=manager)
        assert refused.status_code == 404 and refused.json()["code"] == "user_access_missing"
        body = {
            "org_id": "north",
            "username": "missing",
            "password": "correct-password",
            "role_id": missing,
        }
        refused = client.post("/api/v1/access/users", json=body, headers=manager)
        assert refused.status_code == 404 and refused.json()["code"] == "user_access_missing"
    change |= {"org_id": "south", "role_id": foreign}
    assert client.put("/api/v1/access/users", json=change, headers=manager).status_code == 403


# R-01：组织代码格式与唯一性、名称去空白；只有全组织的系统身份能创建组织。
def test_create_org_rules(client: TestClient) -> None:
    manager = north_manager(client)
    orgs = "/api/v1/access/orgs"
    created = client.post(orgs, json={"code": "east-1", "name": " 东区 "}, headers=KEY)
    assert created.status_code == 200, created.text
    assert created.json() == {"code": "east-1", "name": "东区"}
    again = client.post(orgs, json={"code": "east-1", "name": "东区"}, headers=KEY)
    assert again.status_code == 409 and again.json()["code"] == "user_access_conflict"
    for code in ("North", "no", "a_b", "中文代码"):
        body = {"code": code, "name": "错误代码"}
        assert client.post(orgs, json=body, headers=KEY).status_code == 422, code
    refused = client.post(orgs, json={"code": "west", "name": "西区"}, headers=manager)
    assert refused.status_code == 403
