import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Request

from app.api.identity import CallerDep
from app.api.replies import JobAccepted
from shared.access.caller import Caller
from shared.data.models import Data
from shared.errors.framework import TooManyRequests
from shared.errors.kinds import BusinessError
from shared.modules.contract import Contract


@dataclass(frozen=True)
class FailureLimit:
    name: str
    fields: tuple[str, ...]
    limit: int
    seconds: int
    errors: tuple[type[BusinessError], ...]
    per_source: bool = False
    message: str = "失败次数过多，请稍后再试"


class Run:
    def __init__(self, request: Request, caller: Caller) -> None:
        self.request = request
        self.caller = caller

    async def __call__[In: Data, Out: Data](
        self, item: Contract[In, Out], input: In, *, limits: Sequence[FailureLimit] = ()
    ) -> Out:
        services = self.request.app.state.services
        run_ids = self.request.scope.setdefault("state", {}).setdefault("run_ids", [])
        keys = [(limit, self.failure_key(limit, input)) for limit in limits]
        for limit, key in keys:
            if int(await services.cache.get(key) or 0) >= limit.limit:
                raise TooManyRequests(limit.message)
        try:
            result: Out = await services.runtime.run(
                item,
                input,
                caller=self.caller,
                request_id=getattr(self.request.state, "request_id", ""),
                on_start=run_ids.append,
            )
        except BusinessError as error:
            for limit, key in keys:
                if isinstance(error, limit.errors):
                    await services.cache.incr(key, limit.seconds)
            raise
        for _, key in keys:
            await services.cache.delete(key)
        return result

    def failure_key(self, limit: FailureLimit, input: Data) -> str:
        parts = [str(getattr(input, name)) for name in limit.fields]
        if limit.per_source:
            parts.append(self.request.client.host if self.request.client else "unknown")
        digest = hashlib.sha256("\0".join(parts).encode()).hexdigest()
        return f"failure:{limit.name}:{digest}"

    async def later(self, item: Contract[Any, Any], input: Data, *, key: str = "") -> JobAccepted:
        runtime = self.request.app.state.services.runtime
        job_id = await runtime.submit(
            item,
            input,
            caller=self.caller,
            key=key,
            request_id=getattr(self.request.state, "request_id", ""),
        )
        return JobAccepted(job_id=job_id, state="queued", status_url=f"/api/jobs/{job_id}")


async def get_run(request: Request, caller: CallerDep) -> Run:
    return Run(request, caller)


RunDep = Annotated[Run, Depends(get_run)]
