import asyncio
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncConnection

from shared.access.caller import Caller
from shared.data.models import Data
from shared.flow.runtime import Runtime
from shared.jobs.queue import JobQueue, Ticket
from shared.jobs.revalidation import allowed
from shared.jobs.segmented import run_segments
from shared.scenarios.observations import ObservationPosition


async def invoke(
    runtime: Runtime,
    queue: JobQueue,
    ticket: Ticket,
    input: Data,
    caller: Caller,
    stop: asyncio.Event,
    shutdown_seconds: float,
    finish: Callable[[AsyncConnection, Data, str], Awaitable[None]],
    observation_position: ObservationPosition | None = None,
) -> None:
    binding = runtime.catalog.by_name[ticket.contract]
    plan = runtime.catalog.plan(ticket.contract)
    budget = plan.attempt_timeout if plan and plan.attempt_timeout else binding.contract.timeout
    deadline = runtime.clock.monotonic() + budget
    if plan is not None and plan.segmented:
        await run_segments(
            runtime,
            queue,
            ticket,
            input,
            caller,
            stop,
            shutdown_seconds,
            finish,
            deadline=deadline if plan.attempt_timeout else None,
            observation_position=observation_position,
        )
    else:
        if not await allowed(runtime, queue, ticket, input, caller, deadline):
            return
        await runtime.run(
            binding.contract,
            input,
            caller=caller,
            request_id=ticket.request_id,
            job_id=ticket.id,
            before_commit=finish,
            deadline=deadline,
            observation_position=observation_position
            or ObservationPosition(attempt=ticket.attempt),
        )
