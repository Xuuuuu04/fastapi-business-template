"""
所有声明 stream=True 的操作共享 SSE 入口。流结束后仍保留完整运行记录。
操作是否存在、调用者有没有权限、输入是否合格，都在开始输出之前检查，
这样这三类问题返回正常的 HTTP 状态码（404、401/403、422），不会变成 200 加错误事件。
"""

from typing import Any

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from app.api.identity import CallerDep, require
from shared.errors.kinds import BusinessError, Kind

router = APIRouter(prefix="/api/v1/stream", tags=["流式操作"])


class StreamNotFound(BusinessError):
    code = "stream_not_found"
    kind = Kind.NOT_FOUND
    message = "没有这个可供流式执行的操作"


# 用操作声明的输入类型校验正文，并逐段返回执行结果。
@router.post("/{name}", summary="执行流式操作", operation_id="run_stream")
async def run_stream(
    name: str, body: dict[str, Any], request: Request, caller: CallerDep
) -> StreamingResponse:
    runtime = request.app.state.services.runtime
    binding = runtime.catalog.find(name)
    if binding is None or not binding.contract.stream or not binding.contract.entry:
        raise StreamNotFound(f"没有可供流式执行的操作 {name}")
    require(caller, binding.contract.access)
    try:
        input = binding.contract.input.model_validate(body)
    except ValidationError as error:
        raise RequestValidationError(error.errors(include_url=False)) from None
    chunks = runtime.stream(
        binding.contract,
        input,
        caller=caller,
        request_id=getattr(request.state, "request_id", ""),
    )
    return StreamingResponse(
        chunks, media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
    )
