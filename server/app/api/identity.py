from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.api.identity_resolver import alias_token, resolve_session
from shared.access.caller import ANONYMOUS, DEVELOPER, Caller
from shared.access.keys import find_caller
from shared.access.tokens import verify_token
from shared.errors.framework import NotAllowed, NotSignedIn, TooManyRequests
from shared.errors.kinds import BusinessError, Kind

key_header = APIKeyHeader(
    name="X-API-Key",
    scheme_name="服务密钥",
    description="服务密钥，由 uv run dev make-key 生成并配置到 APP_API_KEYS",
    auto_error=False,
)
bearer_header = HTTPBearer(
    scheme_name="登录令牌", description="登录后取得的访问令牌", auto_error=False
)


async def get_caller(
    request: Request,
    key: Annotated[str | None, Security(key_header)],
    bearer: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_header)],
) -> Caller:
    settings = request.app.state.settings
    if key:
        caller = find_caller(key, settings.api_keys)
        if caller is None:
            await count_request(request, failed_credentials=True)
            raise NotSignedIn("服务密钥无效")
    elif bearer is not None or alias_token(request) is not None:
        token = bearer.credentials if bearer is not None else alias_token(request)
        if token is None:
            raise NotSignedIn("登录令牌无效")
        keys = [settings.jwt_secret, *settings.jwt_previous_secrets]
        try:
            catalog = request.app.state.services.catalog
            if (
                bearer is None or catalog.identity_token == "opaque"
            ) and catalog.identity is not None:
                caller = await resolve_session(request, token)
            else:
                caller = verify_token(
                    token,
                    [item.get_secret_value() for item in keys],
                    settings.jwt_issuer,
                    settings.jwt_audience,
                )
        except BusinessError as error:
            if error.kind == Kind.NOT_SIGNED_IN:
                await count_request(request, failed_credentials=True)
            raise
    elif settings.dev_caller and settings.env == "local":
        caller = DEVELOPER
    else:
        caller = ANONYMOUS
    await count_request(request, caller)
    return caller


async def count_request(
    request: Request, caller: Caller = ANONYMOUS, *, failed_credentials: bool = False
) -> None:
    settings = request.app.state.settings
    source = request.client.host if request.client else "unknown"
    if failed_credentials:
        bucket = f"invalid_credentials:{source}"
    else:
        bucket = caller.id if caller.kind != "anonymous" else f"anonymous:{source}"
    count = await request.app.state.services.cache.incr(f"rate:{bucket}", 60)
    if count > settings.request_rate_per_minute:
        raise TooManyRequests("请求过于频繁，请一分钟后再试")


CallerDep = Annotated[Caller, Depends(get_caller)]


def require(caller: Caller, permission: str) -> None:
    if caller.can(permission):
        return
    if caller.kind == "anonymous":
        raise NotSignedIn("这个接口需要服务密钥")
    raise NotAllowed(f"需要权限 {permission}")
