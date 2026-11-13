from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from shared.errors.kinds import BusinessError, Kind

router = APIRouter(tags=["运行排查"])
PAGE = Path(__file__).with_suffix(".html")


class ConsoleDisabled(BusinessError):
    code = "console_disabled"
    kind = Kind.NOT_FOUND
    message = "排查网页未开启"


@router.get("/system/console", summary="排查网页", include_in_schema=False)
async def console(request: Request) -> HTMLResponse:
    if not request.app.state.settings.console_enabled():
        raise ConsoleDisabled()
    return HTMLResponse(PAGE.read_text(encoding="utf-8"))


@router.get("/system/console.js", include_in_schema=False)
async def console_script(request: Request) -> Response:
    if not request.app.state.settings.console_enabled():
        raise ConsoleDisabled()
    return Response(
        PAGE.with_suffix(".js").read_text(encoding="utf-8"), media_type="text/javascript"
    )
