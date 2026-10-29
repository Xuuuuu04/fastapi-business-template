from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request

from app.api.identity import CallerDep, require
from shared.errors.framework import NotAllowed
from shared.errors.kinds import BusinessError, Kind
from shared.jobs.checkpoint_store import list_segments, progress
from shared.jobs.views import get_job, list_jobs

router = APIRouter(tags=["后台任务"])

PERMISSION = "system.jobs"


class JobMissing(BusinessError):
    code = "job_missing"
    kind = Kind.NOT_FOUND
    message = "任务不存在"


@router.get("/api/jobs/{job_id}", summary="查看任务", operation_id="get_job")
async def job(job_id: str, request: Request, caller: CallerDep) -> dict[str, Any]:
    found = await get_job(request.app.state.services.database, job_id)
    if found is None:
        raise JobMissing()
    if found.caller_id != caller.id and not caller.can(PERMISSION):
        raise NotAllowed("只能查看自己登记的任务")
    result = asdict(found)
    checkpoint = await progress(request.app.state.services.database, job_id)
    if checkpoint is not None:
        result["checkpoint"] = checkpoint
    return result


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


@router.get("/api/jobs/{job_id}/segments", summary="已提交段", operation_id="job_segments")
async def job_segments(
    job_id: str,
    request: Request,
    caller: CallerDep,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    await job(job_id, request, caller)
    found = await list_segments(
        request.app.state.services.database, job_id, after=after, limit=limit
    )
    return {"items": found, "next_after": found[-1]["number"] if found else after}
