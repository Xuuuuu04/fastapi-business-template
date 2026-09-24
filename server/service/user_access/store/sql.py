"""
用户权限的数据访问实现。管理操作始终核对调用者组织，登录按组织代码精确查询。
登录会话和刷新令牌的部分在 sessions.py。
"""

import asyncio
import json
import re

from sqlalchemy import RowMapping, and_, insert, select
from sqlalchemy.exc import IntegrityError

from service.user_access.data import (
    AccessConflict,
    AccessMissing,
    Account,
    LoginFailed,
    OrgCodeInvalid,
    OrgList,
    OrgView,
    RoleList,
    RoleView,
    UserPage,
    UserView,
)
from service.user_access.store.password import DUMMY_HASH, hash_password, verify_password
from service.user_access.store.sessions import SessionStore
from service.user_access.store.tables import orgs, refresh_tokens, roles, users
from shared.public import Caller, Db, NotAllowed

ORG_CODE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$")
PLATFORM_WIDE = ("user_access.system", "system.diagnostics", "system.jobs", "system.*")


class SqlAccessStore(SessionStore):
    # 取得当前步骤的数据库入口和经过验证的调用者。
    def __init__(self, db: Db, caller: Caller) -> None:
        self.db, self.caller = db, caller

    # 只有全组织管理员能创建组织。
    async def create_org(self, code: str, name: str) -> OrgView:
        if self.caller.org_id != "*":
            raise NotAllowed("创建组织需要全组织管理员身份")
        code, name = code.strip(), name.strip()
        if not ORG_CODE.fullmatch(code) or not name:
            raise OrgCodeInvalid()
        try:
            async with self.db.savepoint():
                await self.db.change(insert(orgs).values(code=code, name=name))
        except IntegrityError:
            raise AccessConflict(f"组织代码 {code} 已存在") from None
        return OrgView(code=code, name=name)

    # 普通管理员只看到自己的组织。
    async def list_orgs(self) -> OrgList:
        query = select(orgs).order_by(orgs.c.code)
        if self.caller.org_id != "*":
            self.require_org(self.caller.org_id)
            query = query.where(orgs.c.code == self.caller.org_id)
        return OrgList(items=[OrgView(**dict(row)) for row in await self.db.all(query)])

    # 角色名称在组织内唯一，权限名去重排序后保存。
    async def create_role(self, org_id: str, name: str, permissions: list[str]) -> RoleView:
        self.require_org(org_id)
        if await self.db.first(select(orgs.c.code).where(orgs.c.code == org_id)) is None:
            raise AccessMissing(f"组织 {org_id} 不存在")
        clean = sorted({item.strip() for item in permissions if item.strip()})
        if any(" " in item or "." not in item for item in clean):
            raise AccessConflict("权限名必须写成 模块名.动作")
        self.require_grantable(clean)
        name = name.strip()
        try:
            async with self.db.savepoint():
                row = await self.db.one(
                    insert(roles)
                    .values(org_id=org_id, name=name, permissions=json.dumps(clean))
                    .returning(roles)
                )
        except IntegrityError:
            raise AccessConflict(f"角色 {name} 在组织 {org_id} 中已存在") from None
        return role_view(row)

    # 查询指定组织中的角色。
    async def list_roles(self, org_id: str) -> RoleList:
        self.require_org(org_id)
        rows = await self.db.all(select(roles).where(roles.c.org_id == org_id).order_by(roles.c.id))
        return RoleList(items=[role_view(row) for row in rows])

    # 校验角色归属，在线程中计算密码摘要后创建用户。
    async def create_user(
        self, org_id: str, username: str, password: str, role_id: int
    ) -> UserView:
        self.require_org(org_id)
        await self.require_role(org_id, role_id)
        secret = await asyncio.to_thread(hash_password, password)
        try:
            async with self.db.savepoint():
                row = await self.db.one(
                    insert(users)
                    .values(
                        org_id=org_id,
                        username=username.strip(),
                        password_hash=secret,
                        role_id=role_id,
                        active=True,
                    )
                    .returning(users)
                )
        except IntegrityError:
            raise AccessConflict(f"用户名 {username} 在组织 {org_id} 中已存在") from None
        return user_view(row)

    # 查询指定组织中的用户，不返回密码摘要。
    async def list_users(self, org_id: str, after: str, limit: int) -> UserPage:
        self.require_org(org_id)
        query = select(users).where(users.c.org_id == org_id)
        rows, next_after = await self.db.page_after(query, users.c.id, after, limit)
        return UserPage(items=[user_view(row) for row in rows], next_after=next_after)

    # 角色必须属于同一个组织，修改只影响该组织中的用户；停用时立即作废这个用户的全部会话。
    async def change_user(self, org_id: str, user_id: int, role_id: int, active: bool) -> UserView:
        self.require_org(org_id)
        await self.require_role(org_id, role_id)
        where = and_(users.c.id == user_id, users.c.org_id == org_id)
        values = {"role_id": role_id, "active": active}
        if await self.db.update_tracked(users, where, values) == 0:
            raise AccessMissing(f"组织 {org_id} 中没有用户 {user_id}")
        row = await self.db.one(select(users).where(where))
        if not active:
            await self.revoke(refresh_tokens.c.user_id == user_id)
        return user_view(row)

    # 失败时使用相同的错误；不存在的用户也计算一次 scrypt，减少账号枚举差异。
    async def login(self, org_code: str, username: str, password: str) -> Account:
        query = (
            select(users, roles.c.permissions)
            .join(roles, users.c.role_id == roles.c.id)
            .where(users.c.org_id == org_code, users.c.username == username)
        )
        row = await self.db.first(query)
        saved = row["password_hash"] if row else DUMMY_HASH
        valid = await asyncio.to_thread(verify_password, password, saved)
        if row is None or not valid or not row["active"]:
            raise LoginFailed()
        return Account(
            user_id=row["id"],
            org_id=row["org_id"],
            username=row["username"],
            permissions=json.loads(row["permissions"]),
        )

    # 拒绝管理其他组织或使用没有组织范围的身份。
    def require_org(self, org_id: str) -> None:
        if not org_id or (self.caller.org_id != "*" and self.caller.org_id != org_id):
            raise NotAllowed("不能管理指定组织的数据")

    # 组织角色不能包含跨组织的系统权限，也不能超出授予者自己拥有的权限。
    def require_grantable(self, permissions: list[str]) -> None:
        platform = [item for item in permissions if item in PLATFORM_WIDE]
        if platform:
            raise NotAllowed(f"组织角色不能包含跨组织的系统权限：{'、'.join(platform)}")
        beyond = [item for item in permissions if not self.caller.can(item)]
        if beyond:
            raise NotAllowed(f"只能授予自己拥有的权限，缺少：{'、'.join(beyond)}")

    # 核对角色存在且属于目标组织。
    async def require_role(self, org_id: str, role_id: int) -> None:
        found = await self.db.first(
            select(roles.c.id).where(roles.c.id == role_id, roles.c.org_id == org_id)
        )
        if found is None:
            raise AccessMissing(f"组织 {org_id} 中没有角色 {role_id}")


# 数据库行转成公开角色信息。
def role_view(row: RowMapping) -> RoleView:
    return RoleView(
        id=row["id"],
        org_id=row["org_id"],
        name=row["name"],
        permissions=json.loads(row["permissions"]),
    )


# 数据库行转成不含密码摘要的用户信息。
def user_view(row: RowMapping) -> UserView:
    return UserView(
        id=row["id"],
        org_id=row["org_id"],
        username=row["username"],
        role_id=row["role_id"],
        active=row["active"],
    )
