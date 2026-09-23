"""
健康检查：/health/live 只判断进程能否响应；
/health/ready 判断数据库能否连通、结构是否已迁移到当前版本。
不依赖 worker 和大模型服务，观察服务出问题也不会让接口被判为未就绪。
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from shared.db.schema import current_revision, head_revision
from shared.errors.framework import DatabaseUnavailable

router = APIRouter(prefix="/health", tags=["运行状态"])


# 进程能响应就返回 ok。
@router.get("/live", summary="进程是否存活", operation_id="health_live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


# 数据库可用且结构版本正确时返回 ready，否则返回 503 和原因。
@router.get("/ready", summary="是否可以接收请求", operation_id="health_ready")
async def ready(request: Request) -> JSONResponse:
    database = request.app.state.services.database
    problems = []
    try:
        await database.ping()
        current, head = await current_revision(database), head_revision()
        if current != head:
            shown = current or "未迁移"
            problems.append(f"数据库结构版本是“{shown}”，代码需要“{head}”，请先执行迁移")
    except Exception as error:
        problems.append(f"{DatabaseUnavailable.message}（{type(error).__name__}）")
    status = 200 if not problems else 503
    body = {"status": "ready" if not problems else "not_ready", "problems": problems}
    return JSONResponse(body, status)
