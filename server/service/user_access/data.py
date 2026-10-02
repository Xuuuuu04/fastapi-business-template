"""
用户权限的公开数据与流程数据。密码和刷新令牌只在输入输出中出现，运行记录不保存原值。
"""

from typing import Literal

from shared.public import BusinessError, CursorPage, Data, Kind, Nothing, WorkData, meaning


# 创建组织时接收的代码和名称。
class OrgInput(Data):
    code: str = meaning("组织代码", rule="R-01", min_length=3, max_length=32)
    name: str = meaning("组织名称", rule="R-01", min_length=1, max_length=80)


# 可公开返回的组织代码和名称。
class OrgView(Data):
    code: str = meaning("组织代码", rule="R-01")
    name: str = meaning("组织名称", rule="R-01")


# 调用者可以访问的组织列表。
class OrgList(Data):
    items: list[OrgView] = meaning("可访问的组织")


# 创建角色时接收的组织、名称和权限集合。
class RoleInput(Data):
    org_id: str = meaning("角色所属组织代码", rule="R-02")
    name: str = meaning("角色名称，在组织内唯一", rule="R-02", min_length=1, max_length=64)
    permissions: list[str] = meaning("角色拥有的权限名", rule="R-02")


# 读取角色等组织数据时使用的组织条件。
class OrgQuery(Data):
    org_id: str = meaning("要查询的组织代码", rule="R-04")


# 可公开返回的角色信息及其权限集合。
class RoleView(Data):
    id: int = meaning("角色编号")
    org_id: str = meaning("角色所属组织代码")
    name: str = meaning("角色名称")
    permissions: list[str] = meaning("角色权限")


# 指定组织中可访问的角色列表。
class RoleList(Data):
    items: list[RoleView] = meaning("可访问的角色")


# 创建用户时接收的账号、密码和角色。
class UserInput(Data):
    org_id: str = meaning("用户所属组织代码", rule="R-02")
    username: str = meaning("用户名，在组织内唯一", rule="R-02", min_length=1, max_length=64)
    password: str = meaning("登录密码", rule="R-02", secret=True, min_length=8, max_length=256)
    role_id: int = meaning("角色编号", rule="R-02", gt=0)


# 修改用户角色或启停状态的公开输入。
class UserChange(Data):
    org_id: str = meaning("用户所属组织代码", rule="R-02")
    user_id: int = meaning("要修改的用户编号", gt=0)
    role_id: int = meaning("修改后的角色编号", rule="R-02", gt=0)
    active: bool = meaning("修改后是否允许登录", rule="R-02")


# 可公开返回的用户信息，不包含密码及身份验证密钥。
class UserView(Data):
    id: int = meaning("用户编号")
    org_id: str = meaning("用户所属组织代码")
    username: str = meaning("用户名")
    role_id: int = meaning("角色编号")
    active: bool = meaning("是否允许登录")


UserPage = CursorPage[UserView]


# 按组织与上一页位置查询用户的分页条件。
class UserQuery(Data):
    org_id: str = meaning("要查询的组织代码", rule="R-04")
    after: str = meaning("上一页返回的 next_after", empty="从第一页开始", default="", max_length=40)
    limit: int = meaning("本页最多返回多少条", default=20, ge=1, le=100)


# 登录时提交的组织、账号、密码和两步验证码。
class LoginInput(Data):
    org_code: str = meaning("组织代码", rule="R-03", max_length=32)
    username: str = meaning("用户名", rule="R-03", max_length=64)
    password: str = meaning("密码", rule="R-03", secret=True, max_length=256)
    otp_code: str = meaning(
        "两步验证码", rule="R-09", empty="没有开启两步验证", default="", max_length=10
    )


# 身份验证通过后的用户及当前角色权限，供签发令牌使用。
class Account(Data):
    user_id: int = meaning("用户编号", rule="R-03")
    org_id: str = meaning("用户所属组织", rule="R-03")
    username: str = meaning("用户名", rule="R-03")
    permissions: list[str] = meaning("角色当前的权限，写进访问令牌", rule="R-03")
    otp_step: int = meaning(
        "这次登录用掉的验证码周期", rule="R-09", empty="没有开启两步验证", default=0
    )


# 一次登录或刷新生成的用户身份与刷新令牌。
class SessionGrant(Data):
    account: Account = meaning("登录的用户及其当前权限", rule="R-05")
    refresh_token: str = meaning("新的刷新令牌原文，只在这次返回", rule="R-05", secret=True)
    refresh_expires_at: float = meaning("刷新令牌失效时间", rule="R-05", unit="Unix 秒")


# 刷新会话的处理结果，区分成功、无效与重复使用。
class SessionRenewal(Data):
    grant: SessionGrant | None = meaning(
        "换得的新会话", rule="R-05", empty="刷新令牌无效、过期、已作废或被重复使用"
    )


# 刷新或退出登录时提交的刷新令牌。
class RefreshInput(Data):
    refresh_token: str = meaning(
        "刷新令牌", rule="R-05", secret=True, min_length=20, max_length=200
    )


# 修改密码时提交的原密码和新密码。
class PasswordChange(Data):
    old_password: str = meaning("原密码", rule="R-06", secret=True, max_length=256)
    new_password: str = meaning("新密码", rule="R-06", secret=True, min_length=8, max_length=256)


# 清理过期会话后实际删除的记录数量。
class PurgeResult(Data):
    removed: int = meaning("删除的刷新令牌记录数", rule="R-07")


# 刷新令牌的检查结果，包含状态、会话家族与有效期。
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


# 表示“组织代码、角色名或用户名已存在”的失败，由统一错误入口返回给调用方。
class AccessConflict(BusinessError):
    code = "user_access_conflict"
    kind = Kind.CONFLICT
    message = "组织代码、角色名或用户名已存在"


# 表示“组织、角色或用户不存在”的失败，由统一错误入口返回给调用方。
class AccessMissing(BusinessError):
    code = "user_access_missing"
    kind = Kind.NOT_FOUND
    message = "组织、角色或用户不存在"


# 表示“账号或密码不正确”的失败，由统一错误入口返回给调用方。
class LoginFailed(BusinessError):
    code = "login_failed"
    kind = Kind.NOT_SIGNED_IN
    message = "账号或密码不正确"


# 表示“登录已失效，请重新登录”的失败，由统一错误入口返回给调用方。
class RefreshRejected(BusinessError):
    code = "refresh_rejected"
    kind = Kind.NOT_SIGNED_IN
    message = "登录已失效，请重新登录"


# 组织代码或名称不符合格式要求时的失败，阻止创建无效组织。
class OrgCodeInvalid(BusinessError):
    code = "org_code_invalid"
    kind = Kind.INVALID
    message = "组织代码只能由小写字母、数字和短横线组成，长 3 至 32 字符；名称不能为空"


# 表示“原密码不正确”的失败，由统一错误入口返回给调用方。
class PasswordMismatch(BusinessError):
    code = "password_mismatch"
    kind = Kind.INVALID
    message = "原密码不正确"


# 创建组织时各步骤共享的代码、名称和结果。
class OrgWork(WorkData):
    code: str = meaning("组织代码")
    name: str = meaning("组织名称")
    result: OrgView = meaning("新建的组织")


# 查询可访问组织时各步骤共享的结果。
class OrgListWork(WorkData):
    result: OrgList = meaning("可访问的组织")


# 创建角色时各步骤共享的权限和角色信息。
class RoleWork(WorkData):
    org_id: str = meaning("角色所属组织")
    name: str = meaning("角色名称")
    permissions: list[str] = meaning("角色权限")
    result: RoleView = meaning("新建的角色")


# 查询组织角色时各步骤共享的条件与结果。
class RoleListWork(WorkData):
    org_id: str = meaning("要查询的组织")
    result: RoleList = meaning("角色列表")


# 创建用户时各步骤共享的账号、密码和角色信息。
class UserWork(WorkData):
    org_id: str = meaning("用户所属组织")
    username: str = meaning("用户名")
    password: str = meaning("密码", secret=True)
    role_id: int = meaning("角色编号")
    result: UserView = meaning("新建的用户")


# 查询用户时各步骤共享的分页条件和结果。
class UserListWork(WorkData):
    org_id: str = meaning("要查询的组织")
    after: str = meaning("从哪个位置之后开始")
    limit: int = meaning("本页最多返回多少条")
    result: UserPage = meaning("一页用户，按编号从小到大，不包含密码摘要")


# 修改用户角色或状态时各步骤共享的数据。
class UserChangeWork(WorkData):
    org_id: str = meaning("用户所属组织")
    user_id: int = meaning("要修改的用户编号")
    role_id: int = meaning("修改后的角色")
    active: bool = meaning("修改后的启用状态")
    result: UserView = meaning("修改后的用户")


# 敏感字段保护测试各步骤共享的令牌和公开结果。
class LoginWork(WorkData):
    org_code: str = meaning("组织代码")
    username: str = meaning("用户名")
    password: str = meaning("密码", secret=True)
    otp_code: str = meaning("两步验证码", secret=True)
    account: Account = meaning("经过密码校验的用户")
    result: SessionGrant = meaning("新建的登录会话", secret=True)


# 刷新会话时各步骤共享的令牌、检查状态与新会话。
class RefreshWork(WorkData):
    refresh_token: str = meaning("刷新令牌", secret=True)
    check: TokenCheck = meaning("刷新令牌的检查结果")
    result: SessionRenewal = meaning("换得的新会话", secret=True)


# 退出登录时各步骤共享的刷新令牌和执行结果。
class LogoutWork(WorkData):
    refresh_token: str = meaning("刷新令牌", secret=True)
    result: Nothing = meaning("没有返回内容")


# 修改密码时各步骤共享的用户身份与密码输入。
class PasswordWork(WorkData):
    old_password: str = meaning("原密码", secret=True)
    new_password: str = meaning("新密码", secret=True)
    user_id: int = meaning("检查过原密码的用户编号")
    result: Nothing = meaning("没有返回内容")


# 清理过期会话时各步骤共享的统计结果。
class PurgeWork(WorkData):
    result: PurgeResult = meaning("清理结果")
