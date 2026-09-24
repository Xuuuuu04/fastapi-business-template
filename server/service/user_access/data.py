"""
用户权限的公开数据与流程数据。密码和刷新令牌只在输入输出中出现，运行记录不保存原值。
"""

from typing import Literal

from shared.public import BusinessError, Data, Kind, Nothing, Page, WorkData, meaning


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


UserPage = Page[UserView]


class UserQuery(Data):
    org_id: str = meaning("要查询的组织代码", rule="R-04")
    offset: int = meaning("从第几条开始，从 0 计数", default=0, ge=0)
    limit: int = meaning("本页最多返回多少条", default=20, ge=1, le=100)


class LoginInput(Data):
    org_code: str = meaning("组织代码", rule="R-03", max_length=32)
    username: str = meaning("用户名", rule="R-03", max_length=64)
    password: str = meaning("密码", rule="R-03", secret=True, max_length=256)


class Account(Data):
    user_id: int = meaning("用户编号", rule="R-03")
    org_id: str = meaning("用户所属组织", rule="R-03")
    username: str = meaning("用户名", rule="R-03")
    permissions: list[str] = meaning("角色当前的权限，写进访问令牌", rule="R-03")


class SessionGrant(Data):
    account: Account = meaning("登录的用户及其当前权限", rule="R-05")
    refresh_token: str = meaning("新的刷新令牌原文，只在这次返回", rule="R-05", secret=True)
    refresh_expires_at: float = meaning("刷新令牌失效时间", rule="R-05", unit="Unix 秒")


class SessionRenewal(Data):
    grant: SessionGrant | None = meaning(
        "换得的新会话", rule="R-05", empty="刷新令牌无效、过期、已作废或被重复使用"
    )


class RefreshInput(Data):
    refresh_token: str = meaning(
        "刷新令牌", rule="R-05", secret=True, min_length=20, max_length=200
    )


class PasswordChange(Data):
    old_password: str = meaning("原密码", rule="R-06", secret=True, max_length=256)
    new_password: str = meaning("新密码", rule="R-06", secret=True, min_length=8, max_length=256)


class PurgeResult(Data):
    removed: int = meaning("删除的刷新令牌记录数", rule="R-07")


class TokenCheck(Data):
    status: Literal["active", "reused", "invalid"] = meaning(
        "刷新令牌状态：active 可用，reused 已用过又被提交，invalid 不存在、过期、已作废或用户停用",
        rule="R-05",
    )
    digest: str = meaning("刷新令牌的 SHA-256 摘要", secret=True)
    family_id: str = meaning("刷新令牌所属的登录会话编号；令牌不存在时为空文本", default="")
    started_at: float = meaning("登录会话开始时间；令牌不可用时为 0", unit="Unix 秒", default=0.0)
    account: Account | None = meaning(
        "用户及其当前权限", empty="令牌不可用，不读取用户", default=None
    )


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


class RefreshRejected(BusinessError):
    code = "refresh_rejected"
    kind = Kind.NOT_SIGNED_IN
    message = "登录已失效，请重新登录"


class OrgCodeInvalid(BusinessError):
    code = "org_code_invalid"
    kind = Kind.INVALID
    message = "组织代码只能由小写字母、数字和短横线组成，长 3 至 32 字符；名称不能为空"


class PasswordMismatch(BusinessError):
    code = "password_mismatch"
    kind = Kind.INVALID
    message = "原密码不正确"


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
    offset: int = meaning("从第几条开始")
    limit: int = meaning("本页最多返回多少条")
    result: UserPage = meaning("一页用户，按编号从小到大，不包含密码摘要")


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
    account: Account = meaning("经过密码校验的用户")
    result: SessionGrant = meaning("新建的登录会话", secret=True)


class RefreshWork(WorkData):
    refresh_token: str = meaning("刷新令牌", secret=True)
    check: TokenCheck = meaning("刷新令牌的核对结果")
    result: SessionRenewal = meaning("换得的新会话", secret=True)


class LogoutWork(WorkData):
    refresh_token: str = meaning("刷新令牌", secret=True)
    result: Nothing = meaning("没有返回内容")


class PasswordWork(WorkData):
    old_password: str = meaning("原密码", secret=True)
    new_password: str = meaning("新密码", secret=True)
    user_id: int = meaning("核对过原密码的用户编号")
    result: Nothing = meaning("没有返回内容")


class PurgeWork(WorkData):
    result: PurgeResult = meaning("清理结果")
