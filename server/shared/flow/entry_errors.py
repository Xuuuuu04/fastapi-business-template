import asyncio
from contextlib import suppress
from typing import TYPE_CHECKING, Any, cast

from shared.access.caller import Caller
from shared.db.database import is_readonly_violation, is_unavailable
from shared.errors.framework import (
    DatabaseUnavailable,
    NotAllowed,
    NotSignedIn,
    RemoteResultUnknown,
    RunTimeout,
    StepRuleBroken,
)
from shared.errors.kinds import BusinessError, Kind
from shared.modules.contract import Contract
from shared.records.models import RemoteCallRecord, RunRecord

if TYPE_CHECKING:
    from shared.flow.runtime import Runtime
    from shared.flow.scope import Scope


def check_access(item: Contract[Any, Any], caller: Caller) -> None:
    if caller.can(item.access):
        return
    if caller.kind == "anonymous":
        raise NotSignedIn(f"“{item.title}”需要登录或服务密钥")
    raise NotAllowed(f"没有权限执行“{item.title}”，需要权限 {item.access}")


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


def after_external_write(problem: BaseException, effects: list[RemoteCallRecord]) -> BaseException:
    if not isinstance(problem, Exception):
        return problem
    if isinstance(problem, BusinessError) and problem.kind == Kind.UNKNOWN_RESULT:
        return problem
    if any(call.outcome in ("ok", "unknown") for call in effects):
        return RemoteResultUnknown(
            "已有外部写入成功或结果尚不能确认，后续操作失败；请先查询结果，不要重发整个操作"
        )
    return problem


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


async def settle_entry(
    runtime: "Runtime", scope: "Scope", run: RunRecord, error: BaseException
) -> BaseException:
    problem = translate(error)
    if run.writes != "unknown":
        run.writes = await scope.tx.rollback()
    problem = after_external_write(problem, scope.remote_writes)
    fill_error(run, problem)
    refused = isinstance(problem, NotAllowed | NotSignedIn) and not run.steps
    status = "refused" if refused else "failed"
    await runtime.close_run(run, status)
    with suppress(AttributeError):
        cast(Any, problem).run_id = run.id
    return problem
