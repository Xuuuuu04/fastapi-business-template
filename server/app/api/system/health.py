from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from shared.db.schema import current_revision, head_revision
from shared.errors.framework import DatabaseUnavailable

router = APIRouter(prefix="/health", tags=["运行状态"])


@router.get("/live", summary="进程是否存活", operation_id="health_live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


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
    try:
        await request.app.state.services.cache.get("health:ready")
    except Exception as error:
        problems.append(f"缓存服务不可用（{type(error).__name__}），请检查 APP_CACHE_URL")
    status = 200 if not problems else 503
    body = {"status": "ready" if not problems else "not_ready", "problems": problems}
    return JSONResponse(body, status)
