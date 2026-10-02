"""
任务查询：调用方查看自己登记的任务；拥有 system.jobs 权限的调用方可以列出全部任务。
重试、取消等人工处理只通过命令行 tools.jobs 进行，这里不提供。
"""

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request

from app.api.identity import CallerDep, require
from shared.errors.framework import NotAllowed
from shared.errors.kinds import BusinessError, Kind
from shared.jobs.views import get_job, list_jobs

router = APIRouter(tags=["后台任务"])

PERMISSION = "system.jobs"


# 表示“任务不存在”的失败，由统一错误入口返回给调用方。
class JobMissing(BusinessError):
    code = "job_missing"
    kind = Kind.NOT_FOUND
    message = "任务不存在"


# 查看一个任务的状态和结果；只能查看自己登记的任务。
@router.get("/api/jobs/{job_id}", summary="查看任务", operation_id="get_job")
async def job(job_id: str, request: Request, caller: CallerDep) -> dict[str, Any]:
    found = await get_job(request.app.state.services.database, job_id)
    if found is None:
        raise JobMissing()
    if found.caller_id != caller.id and not caller.can(PERMISSION):
        raise NotAllowed("只能查看自己登记的任务")
    return asdict(found)


# 按状态和操作列出最近的任务。
@router.get("/api/system/jobs", summary="列出任务", operation_id="system_jobs")
async def jobs(
    request: Request,
    caller: CallerDep,
    state: str = "",
    contract: str = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    require(caller, PERMISSION)
    database = request.app.state.services.database
    found = await list_jobs(database, state=state, contract=contract, limit=limit)
    return {"items": [asdict(item) for item in found]}
