from collections.abc import Sequence

import jwt

from shared.access.caller import Caller
from shared.errors.framework import NotSignedIn
from shared.timing.current import now as business_now


def issue_token(
    caller: Caller, secret: str, issuer: str, audience: str, minutes: int
) -> tuple[str, int]:
    now = int(business_now())
    expires = now + minutes * 60
    claims = {
        "sub": caller.id,
        "name": caller.name,
        "org": caller.org_id,
        "permissions": sorted(caller.permissions),
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": expires,
    }
    return jwt.encode(claims, secret, algorithm="HS256"), expires


def verify_token(token: str, secrets: Sequence[str], issuer: str, audience: str) -> Caller:
    for secret in secrets:
        try:
            claims = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                issuer=issuer,
                audience=audience,
                options={
                    "verify_exp": False,
                    "require": ["sub", "org", "permissions", "iss", "aud", "iat", "exp"],
                },
            )
        except jwt.InvalidSignatureError:
            continue
        except jwt.PyJWTError:
            raise NotSignedIn("登录令牌无效或已过期") from None
        exp = claims.get("exp")
        if isinstance(exp, bool) or not isinstance(exp, int | float) or business_now() >= exp:
            raise NotSignedIn("登录令牌无效或已过期")
        return caller_of(claims)
    raise NotSignedIn("登录令牌无效或已过期")


def caller_of(claims: dict[str, object]) -> Caller:
    names = claims.get("permissions")
    if not isinstance(names, list) or not all(isinstance(item, str) for item in names):
        raise NotSignedIn("登录令牌中的权限格式不正确")
    org = claims.get("org")
    if not isinstance(org, str) or not org:
        raise NotSignedIn("登录令牌中的组织编号不正确")
    return Caller(str(claims["sub"]), "user", str(claims.get("name", "")), frozenset(names), org)
