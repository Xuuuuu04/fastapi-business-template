"""
登录会话的数据访问：刷新令牌的签发、轮换、重复使用检查、作废，以及修改自己的密码。
刷新令牌原文只返回给客户端一次，数据库只保存 SHA-256 摘要。
"""

import asyncio
import hashlib
import json
import secrets
import time
from typing import Any

from sqlalchemy import delete, insert, or_, select, update

from service.user_access.data import (
    Account,
    PasswordMismatch,
    SessionGrant,
    SessionRenewal,
    TokenCheck,
)
from service.user_access.store.password import DUMMY_HASH, hash_password, verify_password
from service.user_access.store.tables import refresh_tokens, roles, users
from shared.public import Caller, Db, NotAllowed

REFRESH_SECONDS = 7 * 86400  # R-05：刷新令牌 7 天不用就失效
SESSION_SECONDS = 30 * 86400  # R-05：一次登录最长保持 30 天，之后必须重新输入密码
KEEP_SECONDS = 86400  # R-07：过期或作废一天后删除记录，留一天供排查


# 刷新令牌的摘要；数据库按摘要查找，原文不写入数据库。
def digest_of(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# 保存登录会话并处理刷新、作废和清理。
class SessionStore:
    db: Db
    caller: Caller

    # 登录成功后开始新的登录会话，返回第一个刷新令牌。
    async def start_session(self, account: Account) -> SessionGrant:
        now = time.time()
        return await self.issue(account, secrets.token_hex(16), now, now)

    # 生成刷新令牌并保存摘要；失效时间取“7 天后”和“会话满 30 天”中较早的一个。
    async def issue(
        self, account: Account, family_id: str, started_at: float, now: float
    ) -> SessionGrant:
        token = secrets.token_urlsafe(32)
        expires = min(now + REFRESH_SECONDS, started_at + SESSION_SECONDS)
        await self.db.change(
            insert(refresh_tokens).values(
                token_sha256=digest_of(token),
                family_id=family_id,
                org_id=account.org_id,
                user_id=account.user_id,
                started_at=started_at,
                expires_at=expires,
            )
        )
        return SessionGrant(account=account, refresh_token=token, refresh_expires_at=expires)

    # 查出刷新令牌的状态；可用时同时读取用户当前的启用状态和角色权限。
    async def check_refresh(self, token: str) -> TokenCheck:
        digest = digest_of(token)
        row = await self.db.first(
            select(refresh_tokens).where(refresh_tokens.c.token_sha256 == digest)
        )
        if row is None or row["revoked_at"] is not None or row["expires_at"] <= time.time():
            return TokenCheck(status="invalid", digest=digest)
        family, started = row["family_id"], row["started_at"]
        if row["used_at"] is not None:
            return TokenCheck(status="reused", digest=digest, family_id=family)
        account = await self.account_of(row["user_id"])
        if account is None:
            return TokenCheck(status="invalid", digest=digest, family_id=family)
        return TokenCheck(
            status="active", digest=digest, family_id=family, started_at=started, account=account
        )

    # 可用的令牌换成新令牌；已用过的令牌又被提交，说明可能被盗用，整组会话作废。
    async def rotate(self, check: TokenCheck) -> SessionRenewal:
        if check.status == "reused":
            await self.revoke(refresh_tokens.c.family_id == check.family_id)
            return SessionRenewal(grant=None)
        if check.status != "active" or check.account is None:
            return SessionRenewal(grant=None)
        now = time.time()
        claimed = await self.db.change(
            update(refresh_tokens)
            .where(
                refresh_tokens.c.token_sha256 == check.digest,
                refresh_tokens.c.used_at.is_(None),
                refresh_tokens.c.revoked_at.is_(None),
                refresh_tokens.c.expires_at > now,
            )
            .values(used_at=now)
        )
        if claimed == 0:
            await self.revoke_reused(check.digest, now)
            return SessionRenewal(grant=None)
        grant = await self.issue(check.account, check.family_id, check.started_at, now)
        return SessionRenewal(grant=grant)

    # 在当前写事务中确认竞争失败是否源于重复使用，只作废仍有效的相应会话。
    async def revoke_reused(self, digest: str, now: float) -> None:
        row = await self.db.first(
            select(refresh_tokens).where(refresh_tokens.c.token_sha256 == digest)
        )
        if (
            row is not None
            and row["used_at"] is not None
            and row["revoked_at"] is None
            and row["expires_at"] > now
        ):
            await self.revoke(refresh_tokens.c.family_id == row["family_id"])

    # 退出登录：作废这个刷新令牌所在的整组会话；令牌不存在时什么也不做。
    async def end_session(self, token: str) -> None:
        row = await self.db.first(
            select(refresh_tokens.c.family_id).where(
                refresh_tokens.c.token_sha256 == digest_of(token)
            )
        )
        if row is not None:
            await self.revoke(refresh_tokens.c.family_id == row["family_id"])

    # 作废满足条件、尚未作废的刷新令牌。
    async def revoke(self, condition: Any) -> None:
        await self.db.change(
            update(refresh_tokens)
            .where(condition, refresh_tokens.c.revoked_at.is_(None))
            .values(revoked_at=time.time())
        )

    # 读取启用中的用户和角色当前的权限；用户停用或不存在时返回 None。
    async def account_of(self, user_id: int) -> Account | None:
        row = await self.db.first(
            select(users, roles.c.permissions)
            .join(roles, users.c.role_id == roles.c.id)
            .where(users.c.id == user_id)
        )
        if row is None or not row["active"]:
            return None
        return Account(
            user_id=row["id"],
            org_id=row["org_id"],
            username=row["username"],
            permissions=json.loads(row["permissions"]),
        )

    # 登录用户检查自己的原密码，返回用户编号。
    async def check_own_password(self, password: str) -> int:
        if self.caller.kind != "user":
            raise NotAllowed("只有登录用户可以修改自己的密码")
        row = await self.db.first(
            select(users.c.id, users.c.password_hash).where(
                users.c.id == int(self.caller.id),
                users.c.org_id == self.caller.org_id,
                users.c.active.is_(True),
            )
        )
        saved = row["password_hash"] if row else DUMMY_HASH
        valid = await asyncio.to_thread(verify_password, password, saved)
        if row is None or not valid:
            raise PasswordMismatch()
        return int(row["id"])

    # 保存新密码摘要，并作废这个用户的全部会话，其他设备需要重新登录。
    async def set_password(self, user_id: int, password: str) -> None:
        secret = await asyncio.to_thread(hash_password, password)
        await self.db.update_tracked(users, users.c.id == user_id, {"password_hash": secret})
        await self.revoke(refresh_tokens.c.user_id == user_id)

    # 删除过期或作废超过一天的刷新令牌记录，只允许全组织的系统任务执行。
    async def purge_sessions(self) -> int:
        if self.caller.org_id != "*":
            raise NotAllowed("只有全组织的系统任务可以清理刷新令牌")
        cutoff = time.time() - KEEP_SECONDS
        return await self.db.change(
            delete(refresh_tokens).where(
                or_(refresh_tokens.c.expires_at < cutoff, refresh_tokens.c.revoked_at < cutoff)
            )
        )
