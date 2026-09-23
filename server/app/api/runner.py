"""
路由使用的执行入口 Run：路由只能通过它执行登记过的操作或登记后台任务，不能直接调用模块内部。
运行编号会写进响应头 X-Run-ID。
"""

from typing import Annotated, Any

from fastapi import Depends, Request

from app.api.identity import CallerDep
from app.api.replies import JobAccepted
from shared.access.caller import Caller
from shared.data.models import Data
from shared.modules.contract import Contract


class Run:
    # 绑定当前请求和调用者。
    def __init__(self, request: Request, caller: Caller) -> None:
        self.request = request
        self.caller = caller

    # 执行一个公开操作并返回结果。
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

    # 登记一个后台任务，立即返回任务编号；key 相同的重复请求返回原任务。
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


# 为每个请求创建执行入口。
async def get_run(request: Request, caller: CallerDep) -> Run:
    return Run(request, caller)


RunDep = Annotated[Run, Depends(get_run)]
