"""
签发和校验 HS256 访问令牌。令牌有效期短（默认 15 分钟），权限是签发时的快照；
到期后客户端用刷新令牌换新令牌，届时重新读取用户状态和角色权限。
更换签名密钥时，旧密钥放进 APP_JWT_PREVIOUS_SECRETS，过渡期内旧令牌仍能校验。
"""

import time
from collections.abc import Sequence

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


# 只接受 HS256，依次用当前密钥和旧密钥校验签名，再校验全部必要字段和权限列表类型。
def verify_token(token: str, secrets: Sequence[str], issuer: str, audience: str) -> Caller:
    for secret in secrets:
        try:
            claims = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                issuer=issuer,
                audience=audience,
                options={"require": ["sub", "org", "permissions", "iss", "aud", "iat", "exp"]},
            )
        except jwt.InvalidSignatureError:
            continue
        except jwt.PyJWTError:
            raise NotSignedIn("登录令牌无效或已过期") from None
        return caller_of(claims)
    raise NotSignedIn("登录令牌无效或已过期")


# 把校验通过的令牌内容转成调用者身份。
def caller_of(claims: dict[str, object]) -> Caller:
    names = claims.get("permissions")
    if not isinstance(names, list) or not all(isinstance(item, str) for item in names):
        raise NotSignedIn("登录令牌中的权限格式不正确")
    org = claims.get("org")
    if not isinstance(org, str) or not org:
        raise NotSignedIn("登录令牌中的组织编号不正确")
    return Caller(str(claims["sub"]), "user", str(claims.get("name", "")), frozenset(names), org)
