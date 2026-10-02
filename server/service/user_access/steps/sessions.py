"""
登录会话流程的步骤：登录、刷新、退出、修改密码和清理过期刷新令牌。
先在只读步骤中检查，再在保存步骤中写入，写入的内容能从运行记录中分清。
"""

from service.user_access.data import (
    LoginWork,
    LogoutWork,
    PasswordWork,
    PurgeResult,
    PurgeWork,
    RefreshWork,
)
from service.user_access.store.contract import AccessStore
from shared.public import Note, Nothing, step


# 检查组织、用户名、密码、启用状态和两步验证码，读出角色当前的权限。
@step(
    "校验登录",
    reads=["org_code", "username", "password", "otp_code"],
    writes=["account"],
    rule="R-03",
)
async def check_login(data: LoginWork, store: AccessStore) -> None:
    data.account = await store.login(data.org_code, data.username, data.password, data.otp_code)


# 用掉两步验证码的周期，开始新的登录会话，签发第一个刷新令牌。
@step("建立登录会话", reads=["account"], writes=["result"], rule="R-05", saves=True)
async def create_session(data: LoginWork, store: AccessStore) -> None:
    await store.use_login_step(data.account)
    data.result = await store.start_session(data.account)


# 查出刷新令牌是否可用，以及用户当前是否启用、有哪些权限。
@step("检查刷新令牌", reads=["refresh_token"], writes=["check"], rule="R-05")
async def check_refresh(data: RefreshWork, store: AccessStore) -> None:
    data.check = await store.check_refresh(data.refresh_token)


# 可用时换新令牌；已用过的令牌又被提交时作废整组会话，并在运行记录中说明。
@step("轮换刷新令牌", reads=["check"], writes=["result"], rule="R-05", saves=True)
async def update_session(data: RefreshWork, store: AccessStore, note: Note) -> None:
    if data.check.status == "reused":
        note("已用过的刷新令牌被再次提交，可能已被盗用，整组登录会话已作废")
    data.result = await store.rotate(data.check)


# 作废刷新令牌所在的整组会话。
@step("作废登录会话", reads=["refresh_token"], writes=["result"], rule="R-05", saves=True)
async def mark_revoked(data: LogoutWork, store: AccessStore) -> None:
    await store.end_session(data.refresh_token)
    data.result = Nothing()


# 检查当前登录用户的原密码。
@step("检查原密码", reads=["old_password"], writes=["user_id"], rule="R-06")
async def check_old_password(data: PasswordWork, store: AccessStore) -> None:
    data.user_id = await store.check_own_password(data.old_password)


# 保存新密码，并让这个用户在所有设备上重新登录。
@step(
    "更新密码并作废会话",
    reads=["user_id", "new_password"],
    writes=["result"],
    rule="R-06",
    saves=True,
)
async def update_password(data: PasswordWork, store: AccessStore) -> None:
    await store.set_password(data.user_id, data.new_password)
    data.result = Nothing()


# 删除过期或作废超过一天的刷新令牌记录。
@step("清理过期刷新令牌", writes=["result"], rule="R-07", saves=True)
async def clean_sessions(data: PurgeWork, store: AccessStore) -> None:
    data.result = PurgeResult(removed=await store.purge_sessions())
