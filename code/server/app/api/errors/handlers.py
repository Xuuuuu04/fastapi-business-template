"""
统一业务异常与 HTTP 错误响应。
校验错误只返回字段和说明，内部异常不暴露敏感细节。
"""

import logging
import sqlite3

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api.replies.models import Error, Issue
from service.notes.types import InvalidNote, NoteMissing, TitleUsed

log = logging.getLogger("server")


# 根据已知异常生成统一错误响应。
async def handle(request: Request, error: Exception) -> JSONResponse:
    status, code, message = 500, "internal_error", "服务器内部错误"
    details: list[Issue] = []
    headers = None

    if isinstance(error, NoteMissing):
        status, code, message = 404, "note_missing", "笔记不存在"
    elif isinstance(error, TitleUsed):
        status, code, message = 409, "title_used", "标题已存在"
    elif isinstance(error, InvalidNote):
        status, code, message = 422, "invalid_note", str(error)
    elif isinstance(error, RequestValidationError):
        status, code, message = 422, "invalid_input", "请求参数不符合要求"
        details = [
            Issue(field=".".join(map(str, issue["loc"])), message="字段类型或取值不符合要求")
            for issue in error.errors()
        ]
    elif isinstance(error, HTTPException):
        status, code, message = (
            error.status_code,
            f"http_{error.status_code}",
            str(error.detail),
        )
        headers = error.headers
    elif isinstance(error, sqlite3.OperationalError):
        status, code, message = 503, "db_unavailable", "数据库暂不可用，请检查初始化与连接"

    request_id = getattr(request.state, "request_id", "")
    if status >= 500:
        log.error("request_failed request_id=%s type=%s", request_id, type(error).__name__)
    result = Error(code=code, message=message, request_id=request_id, details=details)
    return JSONResponse(
        status_code=status,
        content=result.model_dump(),
        headers={**(headers or {}), "X-Request-ID": request_id},
    )


# 注册所有已知错误及意外异常的处理方法。
def register(app: FastAPI) -> None:
    for error in (
        NoteMissing,
        TitleUsed,
        InvalidNote,
        RequestValidationError,
        HTTPException,
        sqlite3.OperationalError,
        Exception,
    ):
        app.add_exception_handler(error, handle)
