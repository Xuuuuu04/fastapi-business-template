import logging
from collections.abc import Awaitable, Callable, Iterable
from itertools import islice
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api.middleware import security_headers
from app.api.replies import STATUS, ErrorReply, FieldProblem
from shared.errors.details import safe_exception_text
from shared.errors.kinds import BusinessError, Kind

log = logging.getLogger("server.errors")

Handler = Callable[[Request, Exception], Awaitable[JSONResponse]]

PROBLEM_TEXT = {
    "missing": "缺少这个字段",
    "extra_forbidden": "不允许出现这个字段",
    "string_too_short": "文字太短",
    "string_too_long": "文字太长",
    "greater_than": "数值太小",
    "greater_than_equal": "数值太小",
    "less_than": "数值太大",
    "less_than_equal": "数值太大",
    "too_short": "项目太少",
    "too_long": "项目太多",
    "literal_error": "不是允许的取值",
    "decimal_max_places": "小数位数太多",
    "json_invalid": "不是合法的 JSON",
}


def error_response(
    request: Request, status: int, code: str, kind: str, message: str, **extra: Any
) -> JSONResponse:
    rid = getattr(request.state, "request_id", "")
    body = ErrorReply(code=code, kind=kind, message=message, request_id=rid, **extra)
    headers = {
        name.decode("ascii"): value.decode("ascii")
        for name, value in security_headers(request.app.state.settings.hsts_seconds)
    }
    headers["X-Request-ID"] = rid
    if body.run_id:
        headers["X-Run-ID"] = body.run_id
    return JSONResponse(body.model_dump(), status_code=status, headers=headers)


async def business_error(request: Request, error: BusinessError) -> JSONResponse:
    message = error.detail
    if error.kind == Kind.BROKEN and request.app.state.settings.env == "production":
        message = "服务器内部错误，请用运行编号查询排查信息"
    fields = field_problems(error.fields.items())
    status = STATUS[error.kind]
    return error_response(
        request, status, error.code, error.kind, message, run_id=error.run_id, fields=fields
    )


async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
    fields = field_problems(
        (
            ".".join(
                str(part) for part in issue.get("loc", ()) if part not in ("body", "query", "path")
            ),
            PROBLEM_TEXT.get(str(issue.get("type")), "取值不符合要求"),
        )
        for issue in error.errors()
    )
    message = "请求参数不符合要求"
    return error_response(request, 422, "invalid_input", Kind.INVALID, message, fields=fields)


def field_problems(entries: Iterable[tuple[str, str]]) -> list[FieldProblem]:
    fields = []
    for name, text in islice(entries, 50):
        try:
            if len(name.encode("utf-8")) > 200:
                continue
        except UnicodeEncodeError:
            continue
        problem = text.encode("utf-8", errors="replace")[:300].decode("utf-8", errors="ignore")
        fields.append(FieldProblem(field=name, problem=problem))
    return fields


async def http_error(request: Request, error: HTTPException) -> JSONResponse:
    status = error.status_code
    if status == 404:
        text = "接口不存在，请检查地址和版本号"
        return error_response(request, 404, "route_not_found", Kind.NOT_FOUND, text)
    if status == 405:
        text = "这个接口不支持该请求方法"
        return error_response(request, 405, "method_not_allowed", Kind.INVALID, text)
    kind = Kind.INVALID if status < 500 else Kind.TEMPORARY
    return error_response(request, status, f"http_{status}", kind, str(error.detail))


async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
    run_id = str(getattr(error, "run_id", ""))
    log.error("request_failed run_id=%s error=%s", run_id, safe_exception_text(error))
    message = "服务器内部错误，请用请求编号或运行编号查询排查信息"
    return error_response(request, 500, "internal_error", "unexpected", message, run_id=run_id)


def add_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(BusinessError, cast(Handler, business_error))
    app.add_exception_handler(RequestValidationError, cast(Handler, validation_error))
    app.add_exception_handler(HTTPException, cast(Handler, http_error))
    app.add_exception_handler(Exception, unexpected_error)
