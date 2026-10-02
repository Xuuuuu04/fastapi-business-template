"""
找回密码（R-08）和两步验证（R-09）的步骤。先在只读步骤中检查，再在保存步骤中写入。
"""

from service.user_access.data_security import (
    IssueResetWork,
    OtpCodeWork,
    OtpResetWork,
    OtpStartWork,
    ResetWork,
)
from service.user_access.store.contract import AccessStore
from shared.public import Nothing, step


# 按 R-08 为本组织用户生成一次性重置码，之前没用过的作废。
@step("生成重置码", reads=["org_id", "user_id"], writes=["result"], rule="R-08", saves=True)
async def create_reset_code(data: IssueResetWork, store: AccessStore) -> None:
    data.result = await store.issue_reset(data.org_id, data.user_id)


# 按 R-08 检查重置码与账号是否相符、是否仍然有效。
@step("检查重置码", reads=["org_code", "username", "code"], writes=["user_id"], rule="R-08")
async def check_reset_code(data: ResetWork, store: AccessStore) -> None:
    data.user_id = await store.check_reset(data.org_code, data.username, data.code)


# 用掉重置码，保存新密码并作废全部登录会话。
@step(
    "用重置码设置新密码",
    reads=["code", "user_id", "new_password"],
    writes=["result"],
    rule="R-08",
    saves=True,
)
async def update_reset_password(data: ResetWork, store: AccessStore) -> None:
    await store.use_reset(data.code)
    await store.set_password(data.user_id, data.new_password)
    data.result = Nothing()


# 按 R-09 生成待确认的两步验证密钥。
@step("生成两步验证密钥", writes=["result"], rule="R-09", saves=True)
async def create_otp_secret(data: OtpStartWork, store: AccessStore) -> None:
    data.result = await store.start_otp()


# 按 R-09 用当前验证码确认，开启两步验证。
@step("确认并开启两步验证", reads=["code"], writes=["result"], rule="R-09", saves=True)
async def update_otp_on(data: OtpCodeWork, store: AccessStore) -> None:
    await store.set_own_otp(True, await store.check_own_otp(data.code))
    data.result = Nothing()


# 按 R-09 用当前验证码确认，关闭两步验证并删除密钥。
@step("确认并关闭两步验证", reads=["code"], writes=["result"], rule="R-09", saves=True)
async def update_otp_off(data: OtpCodeWork, store: AccessStore) -> None:
    await store.set_own_otp(False, await store.check_own_otp(data.code))
    data.result = Nothing()


# 按 R-09 由管理员为本组织用户关闭两步验证，记入变更历史。
@step("管理员关闭两步验证", reads=["org_id", "user_id"], writes=["result"], rule="R-09", saves=True)
async def remove_user_otp(data: OtpResetWork, store: AccessStore) -> None:
    await store.reset_otp(data.org_id, data.user_id)
    data.result = Nothing()
