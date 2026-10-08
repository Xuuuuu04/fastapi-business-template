"""
流程查看与当前阶段恢复：查看需系统诊断权限，恢复另需流程管理权限，按组织限制。
"""

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.api.identity import CallerDep, require
from shared.pipelines.member_views import listing as list_members
from shared.pipelines.recovery import resume
from shared.pipelines.views import detail, list_runs

router = APIRouter(tags=["多阶段流程"])


# 版本变化和未知外部结果需分别明确确认，默认都不接受。
class ResumeRequest(BaseModel):
    accept_schema: bool = False
    confirm_unknown: bool = False


# 只列当前组织的摘要，跨组织系统身份需明确拥有组织通配权限。
@router.get("/api/system/pipelines", summary="流程运行", operation_id="pipeline_runs")
async def listing(
    request: Request, caller: CallerDep, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> dict[str, Any]:
    require(caller, "system.diagnostics")
    services = request.app.state.services
    items = await list_runs(services.database, org_id=caller.org_id, limit=limit)
    return {
        "items": items,
        "definitions": [
            {
                "name": pipeline.name,
                "title": pipeline.title,
                "overlap": pipeline.overlap,
                "stages": [
                    {"name": stage.name, "operation": stage.operation.name}
                    for stage in pipeline.stages
                ],
            }
            for pipeline in services.catalog.pipelines.values()
        ],
    }


# 运行记录链接复用已有的运行查看接口，业务内容不在流程摘要里公开。
@router.get("/api/system/pipelines/{run_id}", summary="流程详情", operation_id="pipeline_detail")
async def show(run_id: str, request: Request, caller: CallerDep) -> dict[str, Any]:
    require(caller, "system.diagnostics")
    result = await detail(request.app.state.services.database, run_id, org_id=caller.org_id)
    if result is None:
        raise HTTPException(status_code=404, detail="流程不存在")
    return result


# 先检查组织可见性，再人工恢复当前阶段；框架不会自动重做未知外部效果。
@router.post(
    "/api/system/pipelines/{run_id}/resume", summary="恢复当前阶段", operation_id="pipeline_resume"
)
async def restart(run_id: str, data: ResumeRequest, request: Request, caller: CallerDep) -> dict:
    require(caller, "system.pipelines")
    await show(run_id, request, caller)
    services = request.app.state.services
    message = await resume(
        services.database,
        services.catalog,
        run_id,
        accept_schema=data.accept_schema,
        confirm_unknown=data.confirm_unknown,
    )
    return {"message": message}


# 成员查询先沿用流程组织与权限过滤，只返回有界摘要。
@router.get(
    "/api/system/pipelines/{run_id}/members", summary="扇出成员", operation_id="pipeline_members"
)
async def member_list(
    run_id: str,
    request: Request,
    caller: CallerDep,
    stage: str,
    after: str = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    await show(run_id, request, caller)
    return await list_members(
        request.app.state.services.database, run_id, stage, after=after, limit=limit
    )
