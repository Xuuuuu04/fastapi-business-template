"""
用户权限流程的步骤。组织、角色和用户的约束由存储实现核对，步骤记录对应规则。
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
from service.user_access.store.contract import AccessStore
from shared.public import step


# 创建组织并返回公开信息。
@step("创建组织", reads=["code", "name"], writes=["result"], rule="R-01", saves=True)
async def create_org(data: OrgWork, store: AccessStore) -> None:
    data.result = await store.create_org(data.code, data.name)


# 查询调用者可访问的组织。
@step("查询组织", writes=["result"], rule="R-04")
async def list_orgs(data: OrgListWork, store: AccessStore) -> None:
    data.result = await store.list_orgs()


# 在指定组织建立角色。
@step(
    "创建角色", reads=["org_id", "name", "permissions"], writes=["result"], rule="R-02", saves=True
)
async def create_role(data: RoleWork, store: AccessStore) -> None:
    data.result = await store.create_role(data.org_id, data.name, data.permissions)


# 查询一个组织的角色。
@step("查询角色", reads=["org_id"], writes=["result"], rule="R-04")
async def list_roles(data: RoleListWork, store: AccessStore) -> None:
    data.result = await store.list_roles(data.org_id)


# 创建用户并保存密码摘要。
@step(
    "创建用户",
    reads=["org_id", "username", "password", "role_id"],
    writes=["result"],
    rule="R-02",
    saves=True,
)
async def create_user(data: UserWork, store: AccessStore) -> None:
    data.result = await store.create_user(data.org_id, data.username, data.password, data.role_id)


# 查询一个组织的用户。
@step("查询用户", reads=["org_id"], writes=["result"], rule="R-04")
async def list_users(data: UserListWork, store: AccessStore) -> None:
    data.result = await store.list_users(data.org_id)


# 修改用户角色和启用状态。
@step(
    "调整用户",
    reads=["org_id", "user_id", "role_id", "active"],
    writes=["result"],
    rule="R-02",
    saves=True,
)
async def update_user(data: UserChangeWork, store: AccessStore) -> None:
    data.result = await store.change_user(data.org_id, data.user_id, data.role_id, data.active)


# 校验账号密码并返回可用于签发令牌的身份。
@step("校验登录", reads=["org_code", "username", "password"], writes=["result"], rule="R-03")
async def check_login(data: LoginWork, store: AccessStore) -> None:
    data.result = await store.login(data.org_code, data.username, data.password)
