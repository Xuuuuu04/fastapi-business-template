"""
为每个请求生成编号并记录耗时。
不记录 URL 查询参数、正文和身份凭据。
"""

import logging
from time import perf_counter
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from shared.monitor.trace import request_id

log = logging.getLogger("server")


class RequestLog(BaseHTTPMiddleware):
    # 关联请求与响应并记录处理结果。
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.request_id = uuid4().hex
        token = request_id.set(request.state.request_id)
        start = perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request.state.request_id
            return response
        finally:
            request_id.reset(token)
            route = request.scope.get("route")
            log.info(
                "request_id=%s method=%s route=%s status=%s ms=%.1f",
                request.state.request_id,
                request.method,
                getattr(route, "path", "unmatched"),
                status,
                (perf_counter() - start) * 1000,
            )
