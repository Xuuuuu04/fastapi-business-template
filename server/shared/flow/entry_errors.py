"""
入口操作的权限检查与错误整理。运行记录只保存对排查有用的错误信息。
"""

import asyncio
from typing import Any

from shared.access.caller import Caller
from shared.db.database import is_readonly_violation, is_unavailable
from shared.errors.framework import (
    DatabaseUnavailable,
    NotAllowed,
    NotSignedIn,
    RunTimeout,
    StepRuleBroken,
)
from shared.errors.kinds import BusinessError
from shared.modules.contract import Contract
from shared.records.models import RunRecord


# 没有身份时报未登录，有身份但缺权限时报无权限。
def check_access(item: Contract[Any, Any], caller: Caller) -> None:
    if caller.can(item.access):
        return
    if caller.kind == "anonymous":
        raise NotSignedIn(f"“{item.title}”需要登录或服务密钥")
    raise NotAllowed(f"没有权限执行“{item.title}”，需要权限 {item.access}")


# 把超时、数据库断连和只读违规转成框架的错误种类。
def translate(error: BaseException) -> BaseException:
    if isinstance(error, BusinessError) or not isinstance(error, Exception):
        return error
    if isinstance(error, TimeoutError):
        return RunTimeout("处理超时，已停止等待；已经发出的外部操作可能仍在进行")
    if is_readonly_violation(error):
        return StepRuleBroken("没有声明 saves=True 的步骤试图写入数据库")
    if is_unavailable(error):
        return DatabaseUnavailable()
    return error


# 保存失败步骤、错误种类和安全的错误信息。
def fill_error(run: RunRecord, problem: BaseException) -> None:
    failed = next((step for step in reversed(run.steps) if step.status == "failed"), None)
    run.failed_step = failed.title if failed else ""
    if isinstance(problem, BusinessError):
        run.error_code, run.error_kind, run.error_message = (
            problem.code,
            problem.kind,
            problem.detail,
        )
    elif isinstance(problem, asyncio.CancelledError):
        run.error_code, run.error_kind, run.error_message = "cancelled", "cancelled", "执行被取消"
    else:
        run.error_code, run.error_kind = type(problem).__name__, "unexpected"
        run.error_message = (
            failed.error_message if failed else ""
        ) or f"程序异常：{type(problem).__name__}"
