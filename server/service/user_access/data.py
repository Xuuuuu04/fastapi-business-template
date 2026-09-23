"""
用户权限的公开数据与流程数据。密码只在输入中出现，运行记录不保存原值。
"""

from shared.public import BusinessError, Data, Kind, WorkData, meaning


class OrgInput(Data):
    code: str = meaning("组织代码", rule="R-01", min_length=3, max_length=32)
    name: str = meaning("组织名称", rule="R-01", min_length=1, max_length=80)


class OrgView(Data):
    code: str = meaning("组织代码", rule="R-01")
    name: str = meaning("组织名称", rule="R-01")


class OrgList(Data):
    items: list[OrgView] = meaning("可访问的组织")


class RoleInput(Data):
    org_id: str = meaning("角色所属组织代码", rule="R-02")
    name: str = meaning("角色名称，在组织内唯一", rule="R-02", min_length=1, max_length=64)
    permissions: list[str] = meaning("角色拥有的权限名", rule="R-02")


class OrgQuery(Data):
    org_id: str = meaning("要查询的组织代码", rule="R-04")


class RoleView(Data):
    id: int = meaning("角色编号")
    org_id: str = meaning("角色所属组织代码")
    name: str = meaning("角色名称")
    permissions: list[str] = meaning("角色权限")


class RoleList(Data):
    items: list[RoleView] = meaning("可访问的角色")


class UserInput(Data):
    org_id: str = meaning("用户所属组织代码", rule="R-02")
    username: str = meaning("用户名，在组织内唯一", rule="R-02", min_length=1, max_length=64)
    password: str = meaning("登录密码", rule="R-02", secret=True, min_length=8, max_length=256)
    role_id: int = meaning("角色编号", rule="R-02", gt=0)


class UserChange(Data):
    org_id: str = meaning("用户所属组织代码", rule="R-02")
    user_id: int = meaning("要修改的用户编号", gt=0)
    role_id: int = meaning("修改后的角色编号", rule="R-02", gt=0)
    active: bool = meaning("修改后是否允许登录", rule="R-02")


class UserView(Data):
    id: int = meaning("用户编号")
    org_id: str = meaning("用户所属组织代码")
    username: str = meaning("用户名")
    role_id: int = meaning("角色编号")
    active: bool = meaning("是否允许登录")


class UserList(Data):
    items: list[UserView] = meaning("可访问的用户，不包含密码摘要")


class LoginInput(Data):
    org_code: str = meaning("组织代码", rule="R-03")
    username: str = meaning("用户名", rule="R-03")
    password: str = meaning("密码", rule="R-03", secret=True)


class LoginIdentity(Data):
    user_id: int = meaning("登录成功的用户编号", rule="R-03")
    org_id: str = meaning("用户所属组织", rule="R-03")
    username: str = meaning("用户名", rule="R-03")
    permissions: list[str] = meaning("签发令牌时的权限", rule="R-03")


class AccessConflict(BusinessError):
    code = "user_access_conflict"
    kind = Kind.CONFLICT
    message = "组织代码、角色名或用户名已存在"


class AccessMissing(BusinessError):
    code = "user_access_missing"
    kind = Kind.NOT_FOUND
    message = "组织、角色或用户不存在"


class LoginFailed(BusinessError):
    code = "login_failed"
    kind = Kind.NOT_SIGNED_IN
    message = "账号或密码不正确"


class OrgWork(WorkData):
    code: str = meaning("组织代码")
    name: str = meaning("组织名称")
    result: OrgView = meaning("新建的组织")


class OrgListWork(WorkData):
    result: OrgList = meaning("可访问的组织")


class RoleWork(WorkData):
    org_id: str = meaning("角色所属组织")
    name: str = meaning("角色名称")
    permissions: list[str] = meaning("角色权限")
    result: RoleView = meaning("新建的角色")


class RoleListWork(WorkData):
    org_id: str = meaning("要查询的组织")
    result: RoleList = meaning("角色列表")


class UserWork(WorkData):
    org_id: str = meaning("用户所属组织")
    username: str = meaning("用户名")
    password: str = meaning("密码", secret=True)
    role_id: int = meaning("角色编号")
    result: UserView = meaning("新建的用户")


class UserListWork(WorkData):
    org_id: str = meaning("要查询的组织")
    result: UserList = meaning("用户列表")


class UserChangeWork(WorkData):
    org_id: str = meaning("用户所属组织")
    user_id: int = meaning("要修改的用户编号")
    role_id: int = meaning("修改后的角色")
    active: bool = meaning("修改后的启用状态")
    result: UserView = meaning("修改后的用户")


class LoginWork(WorkData):
    org_code: str = meaning("组织代码")
    username: str = meaning("用户名")
    password: str = meaning("密码", secret=True)
    result: LoginIdentity = meaning("经过密码校验的身份")
