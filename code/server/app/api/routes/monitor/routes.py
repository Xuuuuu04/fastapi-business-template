"""
提供受保护的模块目录、调用快照和流程图。
返回单进程有界记录，不提供数据修改或代码执行能力。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.access.monitor import require_monitor
from app.api.replies.models import ERRORS

router = APIRouter(
    prefix="/api/v1/monitor",
    tags=["运行监控"],
    dependencies=[Depends(require_monitor)],
    responses=ERRORS,
)


# 返回模块版本、公开操作与允许的调用关系。
@router.get("/modules", summary="模块注册目录", operation_id="monitor_modules")
def modules(request: Request) -> dict:
    return request.app.state.registry.describe()


# 返回最近调用或指定请求的实时状态。
@router.get("/traces", summary="模块调用记录", operation_id="monitor_traces")
def traces(
    request: Request,
    request_id: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> dict:
    return request.app.state.monitor.snapshot(request_id, limit)


# 返回静态依赖图或指定请求的实际调用图。
@router.get("/graph", summary="模块调用图", operation_id="monitor_graph")
def graph(
    request: Request,
    request_id: Annotated[str | None, Query(max_length=64)] = None,
) -> dict:
    lines = ["flowchart TD"]
    if request_id is None:
        for module in request.app.state.registry.modules.values():
            lines.append(f'    {module.name}["{module.name} v{module.version}"]')
            for target in module.calls:
                lines.append(f"    {module.name} --> {target}")
        return {"kind": "declared", "mermaid": "\n".join(lines)}
    snapshot = request.app.state.monitor.snapshot(request_id, 1000)
    ids = {row["id"] for row in snapshot["items"]}
    for row in snapshot["items"]:
        label = (
            f"{row['module']}.{row['action']} | {row['status']} | {row['elapsed_ms']:.2f} ms"
        )
        lines.append(f'    span_{row["id"]}["{label}"]')
        if row["parent_id"] in ids:
            lines.append(f"    span_{row['parent_id']} --> span_{row['id']}")
    return {
        "kind": "observed",
        "mermaid": "\n".join(lines),
        "limited": snapshot["limited"],
        "count": snapshot["returned"],
    }
