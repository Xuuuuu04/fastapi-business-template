"""
worker 的显式分段执行：每批重新调用操作并创建事务，不跨批持有连接或业务中间对象。
"""

import asyncio
import time
from time import perf_counter
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.access.caller import Caller
from shared.data.models import Data
from shared.errors.framework import StaleAttempt
from shared.flow.runtime import Hook, Runtime
from shared.jobs import checkpoint_store
from shared.jobs.checkpoint import Checkpoint
from shared.jobs.queue import JobQueue, Ticket


# 从数据库游标恢复；每批成功后继续下一批，最终结果只在 finish 后写入任务。
async def run_segments(
    runtime: Runtime,
    queue: JobQueue,
    ticket: Ticket,
    input: Data,
    caller: Caller,
    stop: asyncio.Event,
    shutdown_seconds: float,
    before_finish: Hook | None = None,
) -> None:
    binding = runtime.catalog.by_name[ticket.contract]
    number, cursor, total_rows = await checkpoint_store.load(runtime.database, ticket.id)
    while True:
        from shared.pipelines.overdue import may_continue

        if not await may_continue(queue, ticket.id):
            await queue.fail(
                ticket, "waiting_retry", "pipeline_overdue_paused", "流程逾期，已在批次边界暂停"
            )
            return
        if stop.is_set():
            await queue.fail(
                ticket, "waiting_retry", "worker_stopping", "已在提交边界停止，等待继续"
            )
            return
        plan = runtime.catalog.plan(ticket.contract)
        if plan is None or not await queue.extend(
            ticket, time.time() + plan.lease_seconds, require_current=True
        ):
            raise StaleAttempt()
        checkpoint = make_checkpoint(runtime, ticket, number, cursor, total_rows, shutdown_seconds)
        commit = commit_batch(queue, ticket, checkpoint, before_finish)
        await runtime.run(
            binding.contract,
            input,
            caller=caller,
            request_id=ticket.request_id,
            job_id=ticket.id,
            before_commit=commit,
            checkpoint=checkpoint,
        )
        if checkpoint.done:
            return
        number, cursor, total_rows = await checkpoint_store.load(runtime.database, ticket.id)


# 写入意图的尝试编号和段号固定在本批，不读取已变化的循环变量。
def make_checkpoint(
    runtime: Runtime,
    ticket: Ticket,
    number: int,
    cursor: dict[str, Any],
    total_rows: int,
    shutdown_seconds: float,
) -> Checkpoint:
    # 所有层级的外部写入共用这个持久化保护。
    async def before_write() -> None:
        await checkpoint_store.mark_external(runtime.database, ticket, number)

    plan = runtime.catalog.plan(ticket.contract)
    return Checkpoint(
        number,
        cursor,
        before_write,
        total_rows=total_rows,
        shutdown_seconds=shutdown_seconds,
        cursor_model=plan.cursor if plan is not None else None,
    )


# 固定本批提交点，段证据与业务结果同事务，最后一批同时完成任务。
def commit_batch(
    queue: JobQueue, ticket: Ticket, checkpoint: Checkpoint, before_finish: Hook | None = None
) -> Hook:
    started = perf_counter()

    # 尝试过期或提交失败时，数据和游标一起回滚。
    async def commit(connection: AsyncConnection, result: Data, run_id: str) -> None:
        await checkpoint_store.save(
            connection, ticket, checkpoint, run_id, (perf_counter() - started) * 1000
        )
        if checkpoint.done and before_finish is not None:
            await before_finish(connection, result, run_id)
        elif checkpoint.done and not await queue.finish(
            connection, ticket, result.model_dump_json(), run_id
        ):
            raise StaleAttempt()

    return commit
