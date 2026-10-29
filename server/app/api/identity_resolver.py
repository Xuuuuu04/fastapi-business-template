from fastapi import Request
from pydantic import ValidationError

from shared.access.caller import ANONYMOUS, Caller
from shared.errors.framework import NotSignedIn


def alias_token(request: Request) -> str | None:
    header = request.app.state.services.catalog.identity_header
    if not header or "authorization" in request.headers:
        return None
    token = request.headers.get(header)
    if token is None:
        return None
    return token[7:].strip() if token.lower().startswith("bearer ") else token.strip()


async def resolve_session(request: Request, token: str) -> Caller:
    operation = request.app.state.services.catalog.identity
    if operation is None or not token or len(token) > 4096:
        raise NotSignedIn("登录令牌无效")
    try:
        input = operation.input.model_validate({"token": token})
    except ValidationError:
        raise NotSignedIn("登录令牌无效") from None
    identity = await request.app.state.services.runtime.run(
        operation, input, caller=ANONYMOUS, record_success=False
    )
    return Caller(
        identity.username, "user", identity.name, frozenset(identity.permissions), identity.org_id
    )
