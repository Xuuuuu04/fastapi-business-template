"""
用户权限模块的公开数据和操作，接口及其他模块只从这里导入。
"""

from service.user_access.data import (
    AccessConflict,
    AccessMissing,
    Account,
    LoginFailed,
    LoginInput,
    OrgCodeInvalid,
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
    UserPage,
    UserQuery,
    UserView,
)
from service.user_access.data_security import (
    OtpCode,
    OtpInvalid,
    OtpRequired,
    OtpSetup,
    ResetCode,
    ResetInput,
    ResetInvalid,
    UserRef,
)
from shared.public import SIGNED_IN, Nothing, contract

create_org = contract(
    "user_access.create_org",
    "创建组织",
    input=OrgInput,
    output=OrgView,
    access="user_access.system",
    errors=(AccessConflict, OrgCodeInvalid),
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
    input=UserQuery,
    output=UserPage,
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
    errors=(LoginFailed, OtpRequired),
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
issue_reset = contract(
    "user_access.issue_reset",
    "生成密码重置码",
    input=UserRef,
    output=ResetCode,
    access="user_access.manage",
    audit=True,
)
reset_password = contract(
    "user_access.reset_password",
    "用重置码设置新密码",
    input=ResetInput,
    output=Nothing,
    access="public",
    errors=(ResetInvalid,),
    audit=True,
)
start_otp = contract(
    "user_access.start_otp",
    "生成两步验证密钥",
    input=Nothing,
    output=OtpSetup,
    access=SIGNED_IN,
    errors=(OtpInvalid,),
    audit=True,
)
enable_otp = contract(
    "user_access.enable_otp",
    "开启两步验证",
    input=OtpCode,
    output=Nothing,
    access=SIGNED_IN,
    errors=(OtpInvalid,),
    audit=True,
)
disable_otp = contract(
    "user_access.disable_otp",
    "关闭两步验证",
    input=OtpCode,
    output=Nothing,
    access=SIGNED_IN,
    errors=(OtpInvalid,),
    audit=True,
)
reset_otp = contract(
    "user_access.reset_otp",
    "管理员关闭两步验证",
    input=UserRef,
    output=Nothing,
    access="user_access.manage",
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
    "OtpCode",
    "OtpInvalid",
    "OtpRequired",
    "OtpSetup",
    "ResetCode",
    "ResetInput",
    "ResetInvalid",
    "UserRef",
    "issue_reset",
    "reset_password",
    "start_otp",
    "enable_otp",
    "disable_otp",
    "reset_otp",
    "AccessConflict",
    "OrgCodeInvalid",
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
    "UserPage",
    "UserQuery",
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
