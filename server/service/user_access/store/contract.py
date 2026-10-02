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
    UserPage,
    UserView,
)
from service.user_access.data_security import OtpSetup, ResetCode


# 用户权限步骤允许使用的数据访问操作，数据库细节集中在实现中。
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
    async def list_users(self, org_id: str, after: str, limit: int) -> UserPage: ...

    # 修改用户的角色与启用状态。
    async def change_user(
        self, org_id: str, user_id: int, role_id: int, active: bool
    ) -> UserView: ...

    # 校验组织、用户名、密码和两步验证码（R-09）。
    async def login(
        self, org_code: str, username: str, password: str, otp_code: str
    ) -> Account: ...

    # 登录成功后用掉验证码周期，防止同一个验证码用两次。
    async def use_login_step(self, account: Account) -> None: ...

    # 管理员为本组织用户生成一次性重置码（R-08）。
    async def issue_reset(self, org_id: str, user_id: int) -> ResetCode: ...

    # 查出重置码对应的用户编号。
    async def check_reset(self, org_code: str, username: str, code: str) -> int: ...

    # 用掉重置码，并发提交时只有一个成功。
    async def use_reset(self, code: str) -> None: ...

    # 生成待确认的两步验证密钥（R-09）。
    async def start_otp(self) -> OtpSetup: ...

    # 检查当前用户的验证码，返回用掉的周期。
    async def check_own_otp(self, code: str) -> int: ...

    # 开启或关闭当前用户的两步验证。
    async def set_own_otp(self, enabled: bool, step: int) -> None: ...

    # 管理员为本组织用户关闭两步验证。
    async def reset_otp(self, org_id: str, user_id: int) -> None: ...

    # 开始新的登录会话，返回第一个刷新令牌。
    async def start_session(self, account: Account) -> SessionGrant: ...

    # 查出刷新令牌的状态和用户当前的权限。
    async def check_refresh(self, token: str) -> TokenCheck: ...

    # 轮换可用的刷新令牌；重复使用时作废整组会话。
    async def rotate(self, check: TokenCheck) -> SessionRenewal: ...

    # 作废刷新令牌所在的整组会话。
    async def end_session(self, token: str) -> None: ...

    # 登录用户检查自己的原密码，返回用户编号。
    async def check_own_password(self, password: str) -> int: ...

    # 保存新密码并作废这个用户的全部会话。
    async def set_password(self, user_id: int, password: str) -> None: ...

    # 删除过期或作废超过一天的刷新令牌记录。
    async def purge_sessions(self) -> int: ...
