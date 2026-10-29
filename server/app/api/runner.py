from typing import Annotated, Any

from fastapi import Depends, Request

from app.api.identity import CallerDep
from app.api.replies import JobAccepted
from shared.access.caller import Caller
from shared.data.models import Data
from shared.modules.contract import Contract


class Run:
    def __init__(self, request: Request, caller: Caller) -> None:
        self.request = request
        self.caller = caller

    async def __call__[In: Data, Out: Data](self, item: Contract[In, Out], input: In) -> Out:
        runtime = self.request.app.state.services.runtime
        run_ids = self.request.scope.setdefault("state", {}).setdefault("run_ids", [])
        result: Out = await runtime.run(
            item,
            input,
            caller=self.caller,
            request_id=getattr(self.request.state, "request_id", ""),
            on_start=run_ids.append,
        )
        return result

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
