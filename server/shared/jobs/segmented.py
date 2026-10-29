import asyncio
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
from shared.jobs.revalidation import allowed
from shared.scenarios.observations import ObservationPosition
from shared.timing.current import now as business_now


async def run_segments(
    runtime: Runtime,
    queue: JobQueue,
    ticket: Ticket,
    input: Data,
    caller: Caller,
    stop: asyncio.Event,
    shutdown_seconds: float,
    before_finish: Hook | None = None,
    *,
    deadline: float | None = None,
    observation_position: ObservationPosition | None = None,
) -> None:
    binding = runtime.catalog.by_name[ticket.contract]
    number, cursor, total_rows = await checkpoint_store.load(runtime.database, ticket.id)
    while True:
        if not await continue_batch(queue, ticket, stop):
            return
        plan = runtime.catalog.plan(ticket.contract)
        if plan is None or not await queue.extend(
            ticket, business_now() + plan.lease_seconds, require_current=True
        ):
            raise StaleAttempt()
        batch_deadline = (
            deadline
            if deadline is not None
            else runtime.clock.monotonic() + binding.contract.timeout
        )
        if not await allowed(runtime, queue, ticket, input, caller, batch_deadline):
            return
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
            deadline=batch_deadline,
            observation_position=observation_position
            or ObservationPosition(attempt=ticket.attempt),
        )
        if checkpoint.done:
            return
        number, cursor, total_rows = await checkpoint_store.load(runtime.database, ticket.id)


def make_checkpoint(
    runtime: Runtime,
    ticket: Ticket,
    number: int,
    cursor: dict[str, Any],
    total_rows: int,
    shutdown_seconds: float,
) -> Checkpoint:
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


def commit_batch(
    queue: JobQueue, ticket: Ticket, checkpoint: Checkpoint, before_finish: Hook | None = None
) -> Hook:
    started = perf_counter()

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


async def continue_batch(queue: JobQueue, ticket: Ticket, stop: asyncio.Event) -> bool:
    from shared.pipelines.overdue import may_continue

    if not await may_continue(queue, ticket.id):
        await queue.fail(
            ticket, "waiting_retry", "pipeline_overdue_paused", "流程逾期，已在批次边界暂停"
        )
        return False
    if stop.is_set():
        await queue.fail(ticket, "waiting_retry", "worker_stopping", "已在提交边界停止，等待继续")
        return False
    return True
