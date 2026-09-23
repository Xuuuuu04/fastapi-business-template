"""
只读审计查询。普通组织管理员只能看本组织；全组织调用者可看全部。
"""

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request

from app.api.identity import CallerDep, require
from shared.access.audit import recent

router = APIRouter(prefix="/api/system", tags=["安全审计"])


# 查询最近的审计元数据，不返回业务正文或密码。
@router.get("/audit", summary="查询审计记录", operation_id="system_audit")
async def audit(
    request: Request,
    caller: CallerDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    require(caller, "system.audit")
    if not caller.org_id:
        return {"items": []}
    selected = "" if caller.org_id == "*" else caller.org_id
    rows = await recent(request.app.state.services.database, limit, selected)
    return {"items": rows}
