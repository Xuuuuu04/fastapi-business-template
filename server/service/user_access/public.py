"""
用户权限模块的公开数据和操作，接口及其他模块只从这里导入。
"""

from service.user_access.data import (
    AccessConflict,
    AccessMissing,
    LoginFailed,
    LoginIdentity,
    LoginInput,
    OrgInput,
    OrgList,
    OrgQuery,
    OrgView,
    RoleInput,
    RoleList,
    RoleView,
    UserChange,
    UserInput,
    UserList,
    UserView,
)
from shared.public import Nothing, contract

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
    output=LoginIdentity,
    access="public",
    errors=(LoginFailed,),
    audit=True,
)

__all__ = [
    "AccessConflict",
    "AccessMissing",
    "LoginFailed",
    "LoginIdentity",
    "LoginInput",
    "OrgInput",
    "OrgList",
    "OrgQuery",
    "OrgView",
    "RoleInput",
    "RoleList",
    "RoleView",
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
]
