"""
用户权限步骤使用的存储约定。
"""

from typing import Protocol

from service.user_access.data import (
    LoginIdentity,
    OrgList,
    OrgView,
    RoleList,
    RoleView,
    UserList,
    UserView,
)


class AccessStore(Protocol):
    # 创建一个全系统唯一的组织。
    async def create_org(self, code: str, name: str) -> OrgView: ...

    # 返回调用者可访问的组织。
    async def list_orgs(self) -> OrgList: ...

    # 创建一个组织内唯一的角色。
    async def create_role(self, org_id: str, name: str, permissions: list[str]) -> RoleView: ...

    # 返回指定组织的角色。
    async def list_roles(self, org_id: str) -> RoleList: ...

    # 创建用户并保存密码摘要。
    async def create_user(
        self, org_id: str, username: str, password: str, role_id: int
    ) -> UserView: ...

    # 返回指定组织的用户。
    async def list_users(self, org_id: str) -> UserList: ...

    # 修改用户的角色与启用状态。
    async def change_user(
        self, org_id: str, user_id: int, role_id: int, active: bool
    ) -> UserView: ...

    # 校验组织、用户名和密码。
    async def login(self, org_code: str, username: str, password: str) -> LoginIdentity: ...
