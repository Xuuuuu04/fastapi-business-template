"""
只读排查网页。页面本身不包含数据，查询仍由已有系统接口检查权限。
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

router = APIRouter(tags=["运行排查"])
PAGE = Path(__file__).with_suffix(".html")


# 本地默认提供排查页；生产环境需要明确开启，所有数据请求仍需权限。
@router.get("/system/console", summary="排查网页", include_in_schema=False)
async def console(request: Request) -> HTMLResponse:
    if not request.app.state.settings.console_enabled():
        raise HTTPException(status_code=404, detail="排查网页未开启")
    return HTMLResponse(PAGE.read_text(encoding="utf-8"))


# 仅在页面开启时提供本地脚本，浏览器不依赖外部图表服务。
@router.get("/system/console.js", include_in_schema=False)
async def console_script(request: Request) -> Response:
    if not request.app.state.settings.console_enabled():
        raise HTTPException(status_code=404, detail="运行页面未开启")
    return Response(
        PAGE.with_suffix(".js").read_text(encoding="utf-8"), media_type="text/javascript"
    )
