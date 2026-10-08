"""
按模块声明解析产品自己的登录会话；仅负责适配，不推定账号、权限或组织。
旧JWT与API-Key处理仍在identity.py，模块没有声明时不接收额外凭据头。
"""

from fastapi import Request
from pydantic import ValidationError

from shared.access.caller import ANONYMOUS, Caller
from shared.errors.framework import NotSignedIn


# 仅没有标准Authorization时读取声明过的兼容头，防止弱凭据覆盖标准入口。
def alias_token(request: Request) -> str | None:
    header = request.app.state.services.catalog.identity_header
    if not header or "authorization" in request.headers:
        return None
    token = request.headers.get(header)
    if token is None:
        return None
    return token[7:].strip() if token.lower().startswith("bearer ") else token.strip()


# 不透明令牌交给已登记操作；格式、账号停用和会话有效期由产品操作明确验证。
async def resolve_session(request: Request, token: str) -> Caller:
    operation = request.app.state.services.catalog.identity
    if operation is None or not token or len(token) > 4096:
        raise NotSignedIn("登录令牌无效")
    try:
        input = operation.input.model_validate({"token": token})
    except ValidationError:
        raise NotSignedIn("登录令牌无效") from None
    identity = await request.app.state.services.runtime.run(operation, input, caller=ANONYMOUS)
    return Caller(
        identity.username, "user", identity.name, frozenset(identity.permissions), identity.org_id
    )
