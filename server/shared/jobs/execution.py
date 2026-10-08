"""
worker调用入口：普通操作保持原事务，显式分段任务使用批次提交点。
"""

import asyncio
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.access.caller import Caller
from shared.data.models import Data
from shared.flow.runtime import Runtime
from shared.jobs.queue import JobQueue, Ticket
from shared.jobs.segmented import run_segments


# 根据任务声明选择执行方式，最终完成回调由worker决定。
async def invoke(
    runtime: Runtime,
    queue: JobQueue,
    ticket: Ticket,
    input: Data,
    caller: Caller,
    stop: asyncio.Event,
    shutdown_seconds: float,
    finish: Callable[[AsyncConnection, Data, str], Awaitable[None]],
) -> None:
    binding = runtime.catalog.by_name[ticket.contract]
    plan = runtime.catalog.plan(ticket.contract)
    if plan is not None and plan.segmented:
        await run_segments(runtime, queue, ticket, input, caller, stop, shutdown_seconds, finish)
    else:
        await runtime.run(
            binding.contract,
            input,
            caller=caller,
            request_id=ticket.request_id,
            job_id=ticket.id,
            before_commit=finish,
        )
