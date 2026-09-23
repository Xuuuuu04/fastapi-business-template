"""
签发和校验 HS256 用户令牌；权限是签发时的快照，到期后重新登录取得新权限。
"""

import time

import jwt

from shared.access.caller import Caller
from shared.errors.framework import NotSignedIn


# 用经过密码验证的用户身份签发有明确签发方、接收方和有效期的令牌。
def issue_token(
    caller: Caller, secret: str, issuer: str, audience: str, minutes: int
) -> tuple[str, int]:
    now = int(time.time())
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


# 只接受 HS256，并校验全部必要字段和权限列表类型。
def verify_token(token: str, secret: str, issuer: str, audience: str) -> Caller:
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            issuer=issuer,
            audience=audience,
            options={"require": ["sub", "org", "permissions", "iss", "aud", "iat", "exp"]},
        )
    except jwt.PyJWTError:
        raise NotSignedIn("登录令牌无效或已过期") from None
    names = claims.get("permissions")
    if not isinstance(names, list) or not all(isinstance(item, str) for item in names):
        raise NotSignedIn("登录令牌中的权限格式不正确")
    if not isinstance(claims.get("org"), str) or not claims["org"]:
        raise NotSignedIn("登录令牌中的组织编号不正确")
    return Caller(
        str(claims["sub"]), "user", str(claims.get("name", "")), frozenset(names), claims["org"]
    )
