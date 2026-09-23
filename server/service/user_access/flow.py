"""
用户权限操作的流程。每个操作由一个受声明约束的步骤完成。
"""

from service.user_access.data import (
    LoginWork,
    OrgListWork,
    OrgWork,
    RoleListWork,
    RoleWork,
    UserChangeWork,
    UserListWork,
    UserWork,
)
from service.user_access.steps import access
from shared.public import Flow

create_org = Flow("创建组织", work=OrgWork, result="result", steps=[access.create_org])
list_orgs = Flow("查询组织", work=OrgListWork, result="result", steps=[access.list_orgs])
create_role = Flow("创建角色", work=RoleWork, result="result", steps=[access.create_role])
list_roles = Flow("查询角色", work=RoleListWork, result="result", steps=[access.list_roles])
create_user = Flow("创建用户", work=UserWork, result="result", steps=[access.create_user])
list_users = Flow("查询用户", work=UserListWork, result="result", steps=[access.list_users])
change_user = Flow("调整用户", work=UserChangeWork, result="result", steps=[access.update_user])
login = Flow("用户登录", work=LoginWork, result="result", steps=[access.check_login])
