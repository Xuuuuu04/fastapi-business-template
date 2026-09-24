"""
用户权限步骤使用的存储约定。
"""

from typing import Protocol

from service.user_access.data import (
    Account,
    OrgList,
    OrgView,
    RoleList,
    RoleView,
    SessionGrant,
    SessionRenewal,
    TokenCheck,
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
    async def login(self, org_code: str, username: str, password: str) -> Account: ...

    # 开始新的登录会话，返回第一个刷新令牌。
    async def start_session(self, account: Account) -> SessionGrant: ...

    # 查出刷新令牌的状态和用户当前的权限。
    async def check_refresh(self, token: str) -> TokenCheck: ...

    # 轮换可用的刷新令牌；重复使用时作废整组会话。
    async def rotate(self, check: TokenCheck) -> SessionRenewal: ...

    # 作废刷新令牌所在的整组会话。
    async def end_session(self, token: str) -> None: ...

    # 登录用户核对自己的原密码，返回用户编号。
    async def check_own_password(self, password: str) -> int: ...

    # 保存新密码并作废这个用户的全部会话。
    async def set_password(self, user_id: int, password: str) -> None: ...

    # 删除过期或作废超过一天的刷新令牌记录。
    async def purge_sessions(self) -> int: ...
