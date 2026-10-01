"""
运行记录查询：最近的运行、一次运行的全部步骤（含下一层调用）、中文诊断报告、进程运行状态。
只读，不提供重试、清理等修改能力。需要权限 system.diagnostics；每次查询都写一条日志。
"""

import logging
import os
import time
from dataclasses import asdict
from typing import Annotated, Any

import psutil
from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse

from app.api.identity import CallerDep, require
from shared.errors.kinds import BusinessError, Kind
from shared.graphs.observed import run_graph, run_report
from shared.jobs.views import count_jobs
from shared.records.recorder import Recorder
from shared.records.stores import RunFilter

log = logging.getLogger("server.diagnostics")

router = APIRouter(prefix="/api/system", tags=["运行诊断"])

PERMISSION = "system.diagnostics"


class RunMissing(BusinessError):
    code = "run_missing"
    kind = Kind.NOT_FOUND
    message = "没有找到这次运行的记录，可能已过期清理或保存时丢失"


# 列出最近的运行，每条带一句中文摘要；同时说明记录是否完整。
@router.get("/runs", summary="最近的运行", operation_id="system_runs")
async def runs(
    request: Request,
    caller: CallerDep,
    module: str = "",
    contract: str = "",
    status: str = "",
    request_id: str = "",
    job_id: str = "",
    before: float | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    require(caller, PERMISSION)
    recorder: Recorder = request.app.state.services.recorder
    rules = RunFilter(module, contract, status, request_id, job_id, before)
    found = await recorder.recent(rules, limit)
    log.info("diagnostics_runs caller=%s count=%s", caller.id, len(found))
    items = [
        {
            "id": run.id,
            "title": run.title,
            "contract": run.contract,
            "status": run.status,
            "started_at": run.started_at,
            "elapsed_ms": run.elapsed_ms,
            "summary": run.summary,
        }
        for run in found
    ]
    return {"items": items, "records": completeness(recorder)}


# 返回一次运行及其下一层调用的全部记录和实际执行图。
@router.get("/runs/{run_id}", summary="一次运行的详情", operation_id="system_run")
async def run_detail(run_id: str, request: Request, caller: CallerDep) -> dict[str, Any]:
    require(caller, PERMISSION)
    tree = await load_tree(request, run_id)
    log.info("diagnostics_run caller=%s run_id=%s", caller.id, run_id)
    root = next(run for run in tree if run.id == run_id)
    runs = [run.to_dict() for run in tree]
    return {"summary": root.summary, "runs": runs, "graph": run_graph(tree)}


# 返回一次运行的中文诊断报告（Markdown），供人阅读和 Agent 排查。
@router.get(
    "/runs/{run_id}/report",
    summary="一次运行的中文诊断报告",
    operation_id="system_run_report",
    response_class=PlainTextResponse,
)
async def run_text(run_id: str, request: Request, caller: CallerDep) -> PlainTextResponse:
    require(caller, PERMISSION)
    tree = await load_tree(request, run_id)
    log.info("diagnostics_report caller=%s run_id=%s", caller.id, run_id)
    return PlainTextResponse(run_report(tree, run_id), media_type="text/markdown; charset=utf-8")


# 返回进程和资源的当前状态：内存、在途请求、连接池、运行记录缓冲、任务数量、熔断状态。
@router.get("/runtime", summary="进程运行状态", operation_id="system_runtime")
async def runtime(request: Request, caller: CallerDep) -> dict[str, Any]:
    require(caller, PERMISSION)
    services = request.app.state.services
    process = psutil.Process(os.getpid())
    try:
        jobs: dict[str, int] | str = await count_jobs(services.database)
    except Exception as error:
        jobs = f"无法读取任务表：{type(error).__name__}"
    return {
        "time": time.time(),
        "env": services.settings.env,
        "code_version": services.settings.code_version,
        "catalog_digest": services.catalog.digest,
        "memory_mb": round(process.memory_info().rss / 1024 / 1024, 1),
        "threads": process.num_threads(),
        "inflight_requests": request.app.state.limits.inflight,
        "database_pool": services.database.engine.pool.status(),
        "records": completeness(services.recorder),
        "jobs": jobs,
        "breakers": {
            **({"model": services.models.breaker.state()} if services.models is not None else {}),
            **{name: item.state() for name, item in services.remotes.breakers.items()},
        },
    }


# 按操作和状态统计已结束的运行，说明尚未保存的记录数。
@router.get("/stats", summary="运行统计", operation_id="system_stats")
async def stats(
    request: Request,
    caller: CallerDep,
    hours: Annotated[int, Query(ge=1, le=24 * 90)] = 24,
    module: str = "",
) -> dict[str, Any]:
    require(caller, PERMISSION)
    recorder: Recorder = request.app.state.services.recorder
    since = time.time() - hours * 3600
    rows = await recorder.stats(since, module)
    log.info("diagnostics_stats caller=%s module=%s hours=%s", caller.id, module, hours)
    return {"since": since, "hours": hours, "items": rows, "records": completeness(recorder)}


# 读取一次运行所在的整棵调用树。
async def load_tree(request: Request, run_id: str) -> list[Any]:
    recorder: Recorder = request.app.state.services.recorder
    found = await recorder.get(run_id)
    if found is None:
        raise RunMissing(f"没有找到运行 {run_id} 的记录")
    tree = await recorder.tree(found.root_id)
    return tree if any(run.id == run_id for run in tree) else [found]


# 说明运行记录的保存方式和丢失情况。
def completeness(recorder: Recorder) -> dict[str, Any]:
    state = asdict(recorder.state())
    state["storage"] = "memory" if recorder.store.immediate else "database"
    lost = state["dropped"] + state["failures"] + state["stored_dropped"]
    missing = f"有 {lost} 条记录因缓冲已满、保存失败或容量限制而缺失"
    state["note"] = "记录完整" if lost == 0 else missing
    return state
