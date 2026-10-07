"""
把异常统一转成错误响应：业务错误、参数校验错误、路由不存在、未预料的程序异常。
内部异常的细节不返回给调用方，只返回请求编号和运行编号，细节用排查接口查询。
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

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


# 生成统一格式的错误响应。
def error_response(
    request: Request, status: int, code: str, kind: str, message: str, **extra: Any
) -> JSONResponse:
    rid = getattr(request.state, "request_id", "")
    body = ErrorReply(code=code, kind=kind, message=message, request_id=rid, **extra)
    headers = {"X-Request-ID": rid}
    if body.run_id:
        headers["X-Run-ID"] = body.run_id
    return JSONResponse(body.model_dump(), status_code=status, headers=headers)


# 业务错误：按错误种类决定状态码；程序与声明不一致时，生产环境只返回通用说明。
async def business_error(request: Request, error: BusinessError) -> JSONResponse:
    message = error.detail
    if error.kind == Kind.BROKEN and request.app.state.settings.env == "production":
        message = "服务器内部错误，请用运行编号查询排查信息"
    fields = [FieldProblem(field=name, problem=text) for name, text in error.fields.items()]
    status = STATUS[error.kind]
    return error_response(
        request, status, error.code, error.kind, message, run_id=error.run_id, fields=fields
    )


# 参数校验错误：逐个字段给出中文说明。
async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
    fields = []
    for issue in error.errors():
        path = [str(part) for part in issue.get("loc", ()) if part not in ("body", "query", "path")]
        text = PROBLEM_TEXT.get(str(issue.get("type")), "取值不符合要求")
        fields.append(FieldProblem(field=".".join(path), problem=text))
    message = "请求参数不符合要求"
    return error_response(request, 422, "invalid_input", Kind.INVALID, message, fields=fields)


# 路由层面的错误：地址不存在、方法不支持等。
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


# 未预料的程序异常：记录日志，只返回编号。
async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
    run_id = str(getattr(error, "run_id", ""))
    log.error("request_failed run_id=%s error=%s", run_id, safe_exception_text(error))
    message = "服务器内部错误，请用请求编号或运行编号查询排查信息"
    return error_response(request, 500, "internal_error", "unexpected", message, run_id=run_id)


# 登记全部错误处理方法；FastAPI 按异常类型调用对应的方法。
def add_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(BusinessError, cast(Handler, business_error))
    app.add_exception_handler(RequestValidationError, cast(Handler, validation_error))
    app.add_exception_handler(HTTPException, cast(Handler, http_error))
    app.add_exception_handler(Exception, unexpected_error)
