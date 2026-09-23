"""
接口共用的返回格式：统一错误响应、任务受理响应，以及按操作生成接口文档中的错误说明。
正常结果直接返回数据本身，不额外包一层；错误使用正确的 HTTP 状态码和稳定的错误码。
"""

from typing import Any

from shared.data.fields import meaning
from shared.data.models import Data
from shared.errors.kinds import KIND_TEXT, Kind
from shared.modules.contract import Contract

STATUS = {
    Kind.INVALID: 422,
    Kind.NOT_FOUND: 404,
    Kind.CONFLICT: 409,
    Kind.NOT_SIGNED_IN: 401,
    Kind.FORBIDDEN: 403,
    Kind.TOO_MANY: 429,
    Kind.TEMPORARY: 503,
    Kind.TIMEOUT: 504,
    Kind.UNKNOWN_RESULT: 502,
    Kind.BROKEN: 500,
}

COMMON = (Kind.INVALID, Kind.NOT_SIGNED_IN, Kind.FORBIDDEN, Kind.TEMPORARY, Kind.BROKEN)


class FieldProblem(Data):
    field: str = meaning("有问题的字段路径，例如 lines.0.quantity")
    problem: str = meaning("问题说明")


class ErrorReply(Data):
    code: str = meaning("稳定的错误码，程序按它判断，不要按说明文字判断")
    kind: str = meaning("错误种类，例如 invalid、not_found、conflict、temporary")
    message: str = meaning("给人看的中文说明")
    request_id: str = meaning("请求编号，用于查日志")
    run_id: str = meaning("运行编号，用于查看执行过程；没有进入业务流程时为空文本", default="")
    fields: list[FieldProblem] = meaning("逐个字段的问题", default_factory=list)


class JobAccepted(Data):
    job_id: str = meaning("任务编号")
    state: str = meaning("任务状态，刚受理时为 queued")
    status_url: str = meaning("查询任务状态的地址")


# 生成接口文档中的错误说明：公共错误加上操作声明的业务错误。
def responses_for(*items: Contract[Any, Any]) -> dict[int | str, dict[str, Any]]:
    codes: dict[int, list[str]] = {STATUS[kind]: [KIND_TEXT[kind]] for kind in COMMON}
    for item in items:
        for error in item.errors:
            codes.setdefault(STATUS[error.kind], []).append(f"{error.code}：{error.message}")
    return {
        status: {"model": ErrorReply, "description": "；".join(texts)}
        for status, texts in sorted(codes.items())
    }
