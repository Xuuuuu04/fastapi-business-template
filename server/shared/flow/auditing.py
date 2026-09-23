"""
操作审计与执行器的事务衔接：成功记录随业务提交，失败记录在回滚后单独保存。
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.access.audit import record as audit_record
from shared.access.audit import record_after as audit_after
from shared.data.models import Data
from shared.db.database import Database
from shared.errors.framework import NotAllowed, NotSignedIn
from shared.flow.scope import Scope
from shared.modules.contract import Contract
from shared.records.models import RunRecord

log = logging.getLogger("server.runtime")
Hook = Callable[[AsyncConnection, Data, str], Awaitable[None]]


# 把调用方的提交前操作和成功审计合并到同一事务。
def audit_hook(item: Contract[Any, Any], scope: Scope, hook: Hook | None) -> Hook | None:
    if not item.audit and hook is None:
        return None

    # 提交前先执行调用方操作，再写审计记录。
    async def combined(connection: AsyncConnection, value: Data, run_id: str) -> None:
        if hook is not None:
            await hook(connection, value, run_id)
        if item.audit:
            await audit_record(connection, scope.caller, item.name, "ok", scope.request_id, run_id)

    return combined


# 失败或权限拒绝在回滚后独立保存；审计故障只写日志。
async def audit_failure(
    database: Database,
    item: Contract[Any, Any],
    scope: Scope,
    run: RunRecord,
    problem: BaseException,
) -> None:
    if not item.audit and not isinstance(problem, NotAllowed | NotSignedIn):
        return
    status = "refused" if isinstance(problem, NotAllowed | NotSignedIn) else "failed"
    try:
        await audit_after(database, scope.caller, item.name, status, scope.request_id, run.id)
    except Exception:
        log.exception("audit_record_failed run_id=%s", run.id)
