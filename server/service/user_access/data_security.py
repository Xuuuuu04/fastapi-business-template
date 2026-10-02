"""
用户权限中与找回密码（R-08）、两步验证（R-09）有关的公开数据、流程数据和业务错误。
从 data.py 按主题拆出，字段写法相同；其他模块和接口层仍只通过 public.py 使用。
"""

from shared.public import BusinessError, Data, Kind, Nothing, WorkData, meaning


# 管理员操作一个用户时提交的组织和用户编号。
class UserRef(Data):
    org_id: str = meaning("用户所属组织代码", rule="R-04", max_length=32)
    user_id: int = meaning("用户编号", gt=0)


# 管理员发放的一次性密码重置码及剩余有效时间。
class ResetCode(Data):
    code: str = meaning("一次性重置码，只返回这一次", rule="R-08", secret=True)
    expires_in: int = meaning("还有多少秒失效", rule="R-08", unit="秒")


# 通过重置码修改密码时提交的账号信息和新密码。
class ResetInput(Data):
    org_code: str = meaning("组织代码", rule="R-08", max_length=32)
    username: str = meaning("用户名", rule="R-08", max_length=64)
    code: str = meaning("管理员给的重置码", rule="R-08", secret=True, max_length=64)
    new_password: str = meaning("新密码", rule="R-08", secret=True, min_length=8, max_length=256)


# 配置两步验证时返回的密钥和身份验证器地址。
class OtpSetup(Data):
    secret: str = meaning("两步验证密钥，填进身份验证器应用", rule="R-09", secret=True)
    uri: str = meaning("可生成二维码的地址", rule="R-09", secret=True)


# 确认或停用两步验证时提交的六位验证码。
class OtpCode(Data):
    code: str = meaning("身份验证器应用显示的 6 位验证码", rule="R-09", min_length=6, max_length=6)


# 表示“需要两步验证码”的失败，由统一错误入口返回给调用方。
class OtpRequired(BusinessError):
    code = "otp_required"
    kind = Kind.NOT_SIGNED_IN
    message = "需要两步验证码"


# 表示“验证码不正确或已用过”的失败，由统一错误入口返回给调用方。
class OtpInvalid(BusinessError):
    code = "otp_invalid"
    kind = Kind.INVALID
    message = "验证码不正确或已用过"


# 表示“重置码无效或已过期”的失败，由统一错误入口返回给调用方。
class ResetInvalid(BusinessError):
    code = "reset_invalid"
    kind = Kind.INVALID
    message = "重置码无效或已过期"


# 管理员发放重置码时各步骤共享的用户条件与结果。
class IssueResetWork(WorkData):
    org_id: str = meaning("用户所属组织")
    user_id: int = meaning("用户编号")
    result: ResetCode = meaning("新的重置码", secret=True)


# 重置密码时各步骤共享的重置码、密码和用户身份。
class ResetWork(WorkData):
    org_code: str = meaning("组织代码")
    username: str = meaning("用户名")
    code: str = meaning("重置码", secret=True)
    new_password: str = meaning("新密码", secret=True)
    user_id: int = meaning("重置码对应的用户编号")
    result: Nothing = meaning("没有返回内容")


# 开始配置两步验证时各步骤共享的临时密钥。
class OtpStartWork(WorkData):
    result: OtpSetup = meaning("待确认的两步验证密钥", secret=True)


# 确认或停用两步验证时各步骤共享的验证码与结果。
class OtpCodeWork(WorkData):
    code: str = meaning("验证码", secret=True)
    result: Nothing = meaning("没有返回内容")


# 管理员重置两步验证时各步骤共享的用户条件与结果。
class OtpResetWork(WorkData):
    org_id: str = meaning("用户所属组织")
    user_id: int = meaning("用户编号")
    result: Nothing = meaning("没有返回内容")
