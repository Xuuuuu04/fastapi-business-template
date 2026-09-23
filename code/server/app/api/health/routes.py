"""
分别检查进程响应和数据库结构就绪状态。
检查只读取本地数据库，不执行迁移。
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.api.replies.models import ERRORS
from shared.db.connect import ready

router = APIRouter(prefix="/health", tags=["运行状态"], responses=ERRORS)


class Health(BaseModel):
    status: str


# 检查当前进程能否响应请求。
@router.get("/live", response_model=Health, summary="进程状态", operation_id="health_live")
def live() -> Health:
    return Health(status="ok")


# 检查数据库是否具备当前应用需要的结构。
@router.get("/ready", response_model=Health, summary="数据库状态", operation_id="health_ready")
def health_ready(request: Request) -> Health:
    if not ready(request.app.state.settings.db_path):
        raise HTTPException(503, "数据库未就绪，请检查初始化状态")
    return Health(status="ready")
