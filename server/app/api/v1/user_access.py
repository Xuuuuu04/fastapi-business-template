"""
组织、角色、用户管理和登录会话接口。业务规则交给 user_access 模块执行，
这里只负责签发访问令牌（签名密钥只在接口层配置中）和登录失败限流。
"""

import hashlib
import time
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, Field

from app.api.replies import responses_for
from app.api.runner import RunDep
from service.user_access import public as access
from shared.access.caller import Caller
from shared.access.tokens import issue_token
from shared.config.settings import Settings
from shared.errors.framework import TooManyRequests
from shared.public import Nothing

router = APIRouter(prefix="/api/v1/access", tags=["用户权限"])


# 登录或刷新成功返回的身份令牌及有效时间。
class TokenReply(BaseModel):
    access_token: str = Field(description="访问令牌，请求时放在 Authorization: Bearer 后面")
    token_type: str = Field(default="Bearer", description="令牌类型，固定为 Bearer")
    expires_in: int = Field(description="访问令牌还有多少秒失效")
    refresh_token: str = Field(description="刷新令牌，只用于换新令牌和退出登录，每次刷新后换新")
    refresh_expires_in: int = Field(description="刷新令牌还有多少秒失效")
    user_id: int = Field(description="用户编号")
    org_id: str = Field(description="用户所属组织")


# 按会话签发访问令牌，返回 OAuth 2.0 通用的令牌字段。
def token_reply(grant: access.SessionGrant, settings: Settings) -> TokenReply:
    account = grant.account
    caller = Caller(
        str(account.user_id),
        "user",
        account.username,
        frozenset(account.permissions),
        account.org_id,
    )
    token, _ = issue_token(
        caller,
        settings.jwt_secret.get_secret_value(),
        settings.jwt_issuer,
        settings.jwt_audience,
        settings.token_minutes,
    )
    return TokenReply(
        access_token=token,
        expires_in=settings.token_minutes * 60,
        refresh_token=grant.refresh_token,
        refresh_expires_in=max(0, int(grant.refresh_expires_at - time.time())),
        user_id=account.user_id,
        org_id=account.org_id,
    )


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


# 分页查询指定组织的用户，按编号从小到大。
@router.get(
    "/users",
    summary="查询用户",
    operation_id="list_users",
    response_model=access.UserPage,
    responses=responses_for(access.list_users),
)
async def list_users(run: RunDep, query: Annotated[access.UserQuery, Query()]) -> access.UserPage:
    return await run(access.list_users, query)


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


# 登录失败分两层限流：同一来源地址对同一账号的失败次数，以及同一账号来自所有地址的失败次数，
# 后者防止攻击者换地址持续猜同一个账号的密码。成功后签发访问令牌和刷新令牌。
@router.post(
    "/login",
    summary="用户登录",
    operation_id="login",
    response_model=TokenReply,
    responses=responses_for(access.login),
)
async def login(body: access.LoginInput, request: Request, run: RunDep) -> TokenReply:
    settings = request.app.state.settings
    source = request.client.host if request.client else "unknown"
    account = f"{body.org_code}:{body.username}"
    keys = {
        failure_key("source", f"{account}:{source}"): settings.login_failure_limit,
        failure_key("account", account): settings.login_account_failure_limit,
    }
    cache = request.app.state.services.cache
    for key, limit in keys.items():
        if int(await cache.get(key) or 0) >= limit:
            raise TooManyRequests("登录失败次数过多，请十五分钟后再试")
    try:
        grant = await run(access.login, body)
    except access.LoginFailed:
        for key in keys:
            await cache.incr(key, 900)
        raise
    for key in keys:
        await cache.delete(key)
    return token_reply(grant, settings)


# 登录失败计数的缓存键；账号和地址先做摘要，缓存中不出现原文。
def failure_key(kind: str, text: str) -> str:
    return f"login-failed:{kind}:{hashlib.sha256(text.encode()).hexdigest()}"


# 用刷新令牌换新的访问令牌和刷新令牌；旧刷新令牌随即作废。
@router.post(
    "/refresh",
    summary="刷新登录",
    operation_id="refresh",
    response_model=TokenReply,
    responses=responses_for(access.refresh),
)
async def refresh(body: access.RefreshInput, request: Request, run: RunDep) -> TokenReply:
    renewal = await run(access.refresh, body)
    if renewal.grant is None:
        raise access.RefreshRejected()
    return token_reply(renewal.grant, request.app.state.settings)


# 退出登录：作废这次登录的全部刷新令牌；令牌无效时同样返回成功，不暴露令牌是否存在。
@router.post(
    "/logout",
    summary="退出登录",
    operation_id="logout",
    status_code=204,
    responses=responses_for(access.logout),
)
async def logout(body: access.RefreshInput, run: RunDep) -> Response:
    await run(access.logout, body)
    return Response(status_code=204)


# 登录用户修改自己的密码；成功后所有设备都需要重新登录。
@router.post(
    "/password",
    summary="修改密码",
    operation_id="change_password",
    status_code=204,
    responses=responses_for(access.change_password),
)
async def change_password(body: access.PasswordChange, run: RunDep) -> Response:
    await run(access.change_password, body)
    return Response(status_code=204)
