"""
组织、角色、用户管理和登录接口。业务规则交给 user_access 模块执行。
"""

import hashlib

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.api.replies import responses_for
from app.api.runner import RunDep
from service.user_access import public as access
from shared.access.caller import Caller
from shared.access.tokens import issue_token
from shared.errors.framework import TooManyRequests
from shared.public import Nothing

router = APIRouter(prefix="/api/v1/access", tags=["用户权限"])


class LoginReply(BaseModel):
    token: str
    token_type: str = "Bearer"
    expires_at: int
    user_id: int
    org_id: str


# 创建组织，只允许全组织管理员。
@router.post(
    "/orgs",
    summary="创建组织",
    operation_id="create_org",
    response_model=access.OrgView,
    responses=responses_for(access.create_org),
)
async def create_org(body: access.OrgInput, run: RunDep) -> access.OrgView:
    return await run(access.create_org, body)


# 查询调用者可访问的组织。
@router.get(
    "/orgs",
    summary="查询组织",
    operation_id="list_orgs",
    response_model=access.OrgList,
    responses=responses_for(access.list_orgs),
)
async def list_orgs(run: RunDep) -> access.OrgList:
    return await run(access.list_orgs, Nothing())


# 在指定组织建立角色。
@router.post(
    "/roles",
    summary="创建角色",
    operation_id="create_role",
    response_model=access.RoleView,
    responses=responses_for(access.create_role),
)
async def create_role(body: access.RoleInput, run: RunDep) -> access.RoleView:
    return await run(access.create_role, body)


# 查询指定组织的角色。
@router.get(
    "/roles",
    summary="查询角色",
    operation_id="list_roles",
    response_model=access.RoleList,
    responses=responses_for(access.list_roles),
)
async def list_roles(org_id: str, run: RunDep) -> access.RoleList:
    return await run(access.list_roles, access.OrgQuery(org_id=org_id))


# 创建用户并以 scrypt 保存密码摘要。
@router.post(
    "/users",
    summary="创建用户",
    operation_id="create_user",
    response_model=access.UserView,
    responses=responses_for(access.create_user),
)
async def create_user(body: access.UserInput, run: RunDep) -> access.UserView:
    return await run(access.create_user, body)


# 查询指定组织的用户。
@router.get(
    "/users",
    summary="查询用户",
    operation_id="list_users",
    response_model=access.UserList,
    responses=responses_for(access.list_users),
)
async def list_users(org_id: str, run: RunDep) -> access.UserList:
    return await run(access.list_users, access.OrgQuery(org_id=org_id))


# 修改用户角色和启用状态。
@router.put(
    "/users",
    summary="调整用户",
    operation_id="change_user",
    response_model=access.UserView,
    responses=responses_for(access.change_user),
)
async def change_user(body: access.UserChange, run: RunDep) -> access.UserView:
    return await run(access.change_user, body)


# 登录失败按组织、用户名和来源地址限流；成功后签发有效期明确的令牌。
@router.post(
    "/login",
    summary="用户登录",
    operation_id="login",
    response_model=LoginReply,
    responses=responses_for(access.login),
)
async def login(body: access.LoginInput, request: Request, run: RunDep) -> LoginReply:
    settings = request.app.state.settings
    source = request.client.host if request.client else "unknown"
    digest = hashlib.sha256(f"{body.org_code}:{body.username}:{source}".encode()).hexdigest()
    key = f"login-failed:{digest}"
    cache = request.app.state.services.cache
    if int(await cache.get(key) or 0) >= settings.login_failure_limit:
        raise TooManyRequests("登录失败次数过多，请十五分钟后再试")
    try:
        identity = await run(access.login, body)
    except access.LoginFailed:
        await cache.incr(key, 900)
        raise
    await cache.delete(key)
    caller = Caller(
        str(identity.user_id),
        "user",
        identity.username,
        frozenset(identity.permissions),
        identity.org_id,
    )
    token, expires = issue_token(
        caller,
        settings.jwt_secret.get_secret_value(),
        settings.jwt_issuer,
        settings.jwt_audience,
        settings.token_minutes,
    )
    return LoginReply(
        token=token, expires_at=expires, user_id=identity.user_id, org_id=identity.org_id
    )
