"""
用户权限操作的流程。管理操作各由一个步骤完成；登录会话的操作先核对、再保存。
"""

from service.user_access.data import (
    LoginWork,
    LogoutWork,
    OrgListWork,
    OrgWork,
    PasswordWork,
    PurgeWork,
    RefreshWork,
    RoleListWork,
    RoleWork,
    UserChangeWork,
    UserListWork,
    UserWork,
)
from service.user_access.steps import access, sessions
from shared.public import Flow

create_org = Flow("创建组织", work=OrgWork, result="result", steps=[access.create_org])
list_orgs = Flow("查询组织", work=OrgListWork, result="result", steps=[access.list_orgs])
create_role = Flow("创建角色", work=RoleWork, result="result", steps=[access.create_role])
list_roles = Flow("查询角色", work=RoleListWork, result="result", steps=[access.list_roles])
create_user = Flow("创建用户", work=UserWork, result="result", steps=[access.create_user])
list_users = Flow("查询用户", work=UserListWork, result="result", steps=[access.list_users])
change_user = Flow("调整用户", work=UserChangeWork, result="result", steps=[access.update_user])
login = Flow(
    "用户登录",
    work=LoginWork,
    result="result",
    steps=[sessions.check_login, sessions.create_session],
)
refresh = Flow(
    "刷新登录",
    work=RefreshWork,
    result="result",
    steps=[sessions.check_refresh, sessions.update_session],
)
logout = Flow("退出登录", work=LogoutWork, result="result", steps=[sessions.mark_revoked])
change_password = Flow(
    "修改密码",
    work=PasswordWork,
    result="result",
    steps=[sessions.check_old_password, sessions.update_password],
)
purge_sessions = Flow(
    "清理过期刷新令牌", work=PurgeWork, result="result", steps=[sessions.clean_sessions]
)
