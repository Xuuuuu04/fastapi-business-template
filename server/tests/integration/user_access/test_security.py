"""
从 HTTP 入口验证找回密码（R-08）和两步验证（R-09）。
"""

import time

from fastapi.testclient import TestClient

from service.user_access.store.totp import PERIOD, code_at
from tests.integration.user_access.test_sessions import LOGIN, bearer, prepare, sign_in
from tests.testing_app import KEY

ACCOUNT = {"org_code": "north", "username": "alice"}


# R-08：管理员生成重置码，用户设置新密码；旧密码、旧会话和用过或被替换的重置码都失效。
def test_reset_password_with_code(client: TestClient) -> None:
    _, _, user_id = prepare(client)
    tokens = sign_in(client)
    issue = {"org_id": "north", "user_id": user_id}
    old_code = client.post("/api/v1/access/users/reset-code", json=issue, headers=KEY).json()
    reply = client.post("/api/v1/access/users/reset-code", json=issue, headers=KEY)
    assert reply.status_code == 200 and reply.json()["expires_in"] == 1800
    code = reply.json()["code"]
    url = "/api/v1/access/password/reset"
    stale = client.post(url, json={**ACCOUNT, "code": old_code["code"], "new_password": "x" * 8})
    assert stale.status_code == 422 and stale.json()["code"] == "reset_invalid"
    wrong_user = {**ACCOUNT, "username": "bob", "code": code, "new_password": "x" * 8}
    assert client.post(url, json=wrong_user).status_code == 422
    body = {**ACCOUNT, "code": code, "new_password": "reset-password-1"}
    assert client.post(url, json=body).status_code == 204
    assert client.post(url, json=body).json()["code"] == "reset_invalid"
    refresh = {"refresh_token": tokens["refresh_token"]}
    assert client.post("/api/v1/access/refresh", json=refresh).status_code == 401
    sign_in(client, "reset-password-1")


# R-09：开启后只提交密码返回 otp_required；同一验证码不能用两次；用户可以自己关闭。
def test_otp_login(client: TestClient) -> None:
    prepare(client)
    user = bearer(sign_in(client))
    setup = client.post("/api/v1/access/otp", headers=user).json()
    assert setup["uri"].startswith("otpauth://totp/")
    step = int(time.time() // PERIOD)
    secret = setup["secret"]
    far = {"code": code_at(secret, step + 5)}
    assert client.post("/api/v1/access/otp/enable", json=far, headers=user).status_code == 422
    enable = {"code": code_at(secret, step)}
    assert client.post("/api/v1/access/otp/enable", json=enable, headers=user).status_code == 204
    password = {**ACCOUNT, "password": "correct-password"}
    needed = client.post(LOGIN, json=password)
    assert needed.status_code == 401 and needed.json()["code"] == "otp_required"
    assert (
        client.post(LOGIN, json={**password, "otp_code": code_at(secret, step)}).status_code == 401
    )
    fresh = {**password, "otp_code": code_at(secret, step + 1)}
    assert client.post(LOGIN, json=fresh).status_code == 200
    assert client.post(LOGIN, json=fresh).status_code == 401
    disable = {"code": code_at(secret, step - 1)}
    assert client.post("/api/v1/access/otp/disable", json=disable, headers=user).status_code == 422


# R-09：手机丢失时管理员关闭两步验证，之后只需密码即可登录，关闭记入变更历史。
def test_admin_resets_otp(client: TestClient) -> None:
    _, _, user_id = prepare(client)
    user = bearer(sign_in(client))
    secret = client.post("/api/v1/access/otp", headers=user).json()["secret"]
    code = {"code": code_at(secret, int(time.time() // PERIOD))}
    client.post("/api/v1/access/otp/enable", json=code, headers=user)
    body = {"org_id": "north", "user_id": user_id}
    assert client.post("/api/v1/access/users/otp/reset", json=body, headers=KEY).status_code == 204
    sign_in(client)
    history = client.get("/api/system/changes?table=user_access_users", headers=KEY).json()
    changed: dict[str, dict[str, str]] = {}
    for item in history["items"]:
        changed.setdefault(item["field"], item)
    assert changed["otp_enabled"]["after"] == "False"
    assert changed["otp_secret"]["before"] == "（已隐藏）"
