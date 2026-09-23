"""
识别调用者身份：请求头 X-API-Key 带服务密钥时按密钥识别；本地开发可以开启开发者身份；其余为匿名。
身份只来自已验证的凭据，请求正文里自报的身份一律不采用。
接入用户登录（例如 JWT）时，在这里增加一种识别方式，业务模块不需要改动。
"""

from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader

from shared.access.caller import ANONYMOUS, DEVELOPER, Caller
from shared.access.keys import find_caller
from shared.errors.framework import NotAllowed, NotSignedIn

key_header = APIKeyHeader(
    name="X-API-Key",
    scheme_name="服务密钥",
    description="服务密钥，由 tools.make_key 生成并配置到 APP_API_KEYS",
    auto_error=False,
)


# 按请求头识别调用者。
async def get_caller(request: Request, key: Annotated[str | None, Security(key_header)]) -> Caller:
    settings = request.app.state.settings
    if key:
        caller = find_caller(key, settings.api_keys)
        if caller is None:
            raise NotSignedIn("服务密钥无效")
        return caller
    if settings.dev_caller and settings.env == "local":
        return DEVELOPER
    return ANONYMOUS


CallerDep = Annotated[Caller, Depends(get_caller)]


# 检查调用者是否拥有系统接口需要的权限。
def require(caller: Caller, permission: str) -> None:
    if caller.can(permission):
        return
    if caller.kind == "anonymous":
        raise NotSignedIn("这个接口需要服务密钥")
    raise NotAllowed(f"需要权限 {permission}")
