"""
找回密码（R-08）和两步验证（R-09）的数据访问。重置码只保存摘要；两步验证密钥用 Vault 加密保存。
用掉重置码、用掉验证码周期都用带条件修改，两个请求同时提交时只有一个成功。
"""

import hashlib
import secrets
import time
from collections.abc import Callable, Mapping
from typing import Any

from sqlalchemy import and_, insert, or_, select, update

from service.user_access.data import Account, LoginFailed
from service.user_access.data_security import (
    OtpInvalid,
    OtpRequired,
    OtpSetup,
    ResetCode,
    ResetInvalid,
)
from service.user_access.store.tables import reset_codes, users
from service.user_access.store.totp import matched_step, new_secret, setup_uri
from shared.public import Caller, Db, NotAllowed, Vault

RESET_SECONDS = 30 * 60  # R-08：重置码 30 分钟内有效
ISSUER = "backend-template"


# 重置码的摘要；数据库按摘要查找，原文不写入数据库。
def code_digest(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


# 保存密码重置与两步验证数据，检查组织范围和用户身份。
class SecurityStore:
    db: Db
    caller: Caller
    vault: Vault
    require_org: Callable[[str], None]

    # 管理员为本组织用户生成重置码；之前没用过的重置码作废。
    async def issue_reset(self, org_id: str, user_id: int) -> ResetCode:
        self.require_org(org_id)
        await self.require_user(org_id, user_id)
        now = time.time()
        await self.db.change(
            update(reset_codes)
            .where(reset_codes.c.user_id == user_id, reset_codes.c.used_at.is_(None))
            .values(used_at=now)
        )
        code = secrets.token_urlsafe(16)
        await self.db.change(
            insert(reset_codes).values(
                code_sha256=code_digest(code),
                org_id=org_id,
                user_id=user_id,
                created_by=f"{self.caller.kind}:{self.caller.id}",
                expires_at=now + RESET_SECONDS,
            )
        )
        return ResetCode(code=code, expires_in=RESET_SECONDS)

    # 查出重置码对应的用户；不对、过期、用过或与账号不符都报同一个错误。
    async def check_reset(self, org_code: str, username: str, code: str) -> int:
        row = await self.db.first(
            select(reset_codes.c.user_id)
            .join(users, users.c.id == reset_codes.c.user_id)
            .where(
                reset_codes.c.code_sha256 == code_digest(code),
                reset_codes.c.used_at.is_(None),
                reset_codes.c.expires_at > time.time(),
                users.c.org_id == org_code,
                users.c.username == username,
            )
        )
        if row is None:
            raise ResetInvalid()
        return int(row["user_id"])

    # 用掉重置码：只有还没用过的才能用掉，并发提交时只有一个成功。
    async def use_reset(self, code: str) -> None:
        await self.db.change_or_fail(
            update(reset_codes)
            .where(reset_codes.c.code_sha256 == code_digest(code), reset_codes.c.used_at.is_(None))
            .values(used_at=time.time()),
            ResetInvalid(),
        )

    # 登录用户生成待确认的两步验证密钥；已经开启时拒绝，需要先关闭。
    async def start_otp(self) -> OtpSetup:
        user_id = self.own_user_id()
        secret = new_secret()
        await self.db.change_or_fail(
            update(users)
            .where(users.c.id == user_id, users.c.otp_enabled.is_(False))
            .values(otp_secret=self.vault.encrypt(secret), otp_last_step=None),
            OtpInvalid("已经开启两步验证，请先关闭再重新设置"),
        )
        return OtpSetup(secret=secret, uri=setup_uri(secret, ISSUER, self.caller.name))

    # 检查当前登录用户的验证码，返回用掉的周期；没有密钥或验证码不对时报错。
    async def check_own_otp(self, code: str) -> int:
        row = await self.db.first(
            select(users.c.otp_secret, users.c.otp_last_step).where(
                users.c.id == self.own_user_id()
            )
        )
        if row is None or not row["otp_secret"]:
            raise OtpInvalid("还没有生成两步验证密钥")
        secret = self.vault.decrypt(row["otp_secret"])
        step = matched_step(secret, code, time.time(), row["otp_last_step"])
        if step is None:
            raise OtpInvalid()
        return step

    # 开启或关闭当前用户的两步验证，同时记下用掉的周期；关闭时删除密钥。
    async def set_own_otp(self, enabled: bool, step: int) -> None:
        values: dict[str, Any] = {"otp_enabled": enabled, "otp_last_step": step}
        if not enabled:
            values |= {"otp_secret": None}
        await self.db.update_tracked(users, users.c.id == self.own_user_id(), values)

    # 管理员为本组织用户关闭两步验证（例如手机丢失），记入变更历史。
    async def reset_otp(self, org_id: str, user_id: int) -> None:
        self.require_org(org_id)
        await self.require_user(org_id, user_id)
        where = and_(users.c.id == user_id, users.c.org_id == org_id)
        values = {"otp_enabled": False, "otp_secret": None, "otp_last_step": None}
        await self.db.update_tracked(users, where, values)

    # 登录时的两步验证：没开启时返回 0；开启了却没提交验证码报 otp_required；不对按登录失败处理。
    def login_step(self, row: Mapping[Any, Any] | None, code: str) -> int:
        if row is None or not row["otp_enabled"]:
            return 0
        if not code:
            raise OtpRequired()
        secret = self.vault.decrypt(str(row["otp_secret"]))
        last = row["otp_last_step"]
        step = matched_step(secret, code, time.time(), int(last) if last is not None else None)
        if step is None:
            raise LoginFailed()
        return step

    # 登录成功后用掉验证码周期：已被别的请求用掉时按登录失败处理，防止同一个验证码用两次。
    async def use_login_step(self, account: Account) -> None:
        if not account.otp_step:
            return
        last = users.c.otp_last_step
        await self.db.change_or_fail(
            update(users)
            .where(
                users.c.id == account.user_id,
                or_(last.is_(None), last < account.otp_step),
            )
            .values(otp_last_step=account.otp_step),
            LoginFailed(),
        )

    # 调用者必须是登录用户本人。
    def own_user_id(self) -> int:
        if self.caller.kind != "user":
            raise NotAllowed("只有登录用户可以设置自己的两步验证")
        return int(self.caller.id)

    # 检查用户属于指定组织。
    async def require_user(self, org_id: str, user_id: int) -> None:
        found = await self.db.first(
            select(users.c.id).where(users.c.id == user_id, users.c.org_id == org_id)
        )
        if found is None:
            raise NotAllowed(f"组织 {org_id} 中没有用户 {user_id}")
