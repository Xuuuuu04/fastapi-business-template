"""
用户权限模块的公开数据和操作，接口及其他模块只从这里导入。
"""

from service.user_access.data import (
    AccessConflict,
    AccessMissing,
    Account,
    LoginFailed,
    LoginInput,
    OrgInput,
    OrgList,
    OrgQuery,
    OrgView,
    PasswordChange,
    PasswordMismatch,
    PurgeResult,
    RefreshInput,
    RefreshRejected,
    RoleInput,
    RoleList,
    RoleView,
    SessionGrant,
    SessionRenewal,
    UserChange,
    UserInput,
    UserList,
    UserView,
)
from shared.public import SIGNED_IN, Nothing, contract

create_org = contract(
    "user_access.create_org",
    "创建组织",
    input=OrgInput,
    output=OrgView,
    access="user_access.system",
    errors=(AccessConflict,),
    audit=True,
)
list_orgs = contract(
    "user_access.list_orgs", "查询组织", input=Nothing, output=OrgList, access="user_access.manage"
)
create_role = contract(
    "user_access.create_role",
    "创建角色",
    input=RoleInput,
    output=RoleView,
    access="user_access.manage",
    errors=(AccessConflict, AccessMissing),
    audit=True,
)
list_roles = contract(
    "user_access.list_roles",
    "查询角色",
    input=OrgQuery,
    output=RoleList,
    access="user_access.manage",
)
create_user = contract(
    "user_access.create_user",
    "创建用户",
    input=UserInput,
    output=UserView,
    access="user_access.manage",
    errors=(AccessConflict, AccessMissing),
    audit=True,
)
list_users = contract(
    "user_access.list_users",
    "查询用户",
    input=OrgQuery,
    output=UserList,
    access="user_access.manage",
)
change_user = contract(
    "user_access.change_user",
    "调整用户",
    input=UserChange,
    output=UserView,
    access="user_access.manage",
    errors=(AccessMissing,),
    audit=True,
)
login = contract(
    "user_access.login",
    "用户登录",
    input=LoginInput,
    output=SessionGrant,
    access="public",
    errors=(LoginFailed,),
    audit=True,
)
refresh = contract(
    "user_access.refresh",
    "刷新登录",
    input=RefreshInput,
    output=SessionRenewal,
    access="public",
    errors=(RefreshRejected,),
    audit=True,
)
logout = contract(
    "user_access.logout",
    "退出登录",
    input=RefreshInput,
    output=Nothing,
    access="public",
    audit=True,
)
change_password = contract(
    "user_access.change_password",
    "修改密码",
    input=PasswordChange,
    output=Nothing,
    access=SIGNED_IN,
    errors=(PasswordMismatch,),
    audit=True,
)
purge_sessions = contract(
    "user_access.purge_sessions",
    "清理过期刷新令牌",
    input=Nothing,
    output=PurgeResult,
    access="user_access.system",
    timeout=120,
)

__all__ = [
    "AccessConflict",
    "AccessMissing",
    "Account",
    "LoginFailed",
    "LoginInput",
    "OrgInput",
    "OrgList",
    "OrgQuery",
    "OrgView",
    "PasswordChange",
    "PasswordMismatch",
    "PurgeResult",
    "RefreshInput",
    "RefreshRejected",
    "RoleInput",
    "RoleList",
    "RoleView",
    "SessionGrant",
    "SessionRenewal",
    "UserChange",
    "UserInput",
    "UserList",
    "UserView",
    "create_org",
    "list_orgs",
    "create_role",
    "list_roles",
    "create_user",
    "list_users",
    "change_user",
    "login",
    "refresh",
    "logout",
    "change_password",
    "purge_sessions",
]
