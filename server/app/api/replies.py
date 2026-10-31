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
    code: str = meaning("错误码；调用方应按此字段处理错误，中文说明可能调整")
    kind: str = meaning("错误种类，例如 invalid、not_found、conflict、temporary")
    message: str = meaning("错误的中文说明，供使用者排查原因")
    request_id: str = meaning("请求编号，用于查日志")
    run_id: str = meaning("运行编号，用于查看执行过程；没有进入业务流程时为空文本", default="")
    fields: list[FieldProblem] = meaning(
        "输入字段的具体问题，最多返回 50 项；修正后重新提交可查看其余问题", default_factory=list
    )


class JobAccepted(Data):
    job_id: str = meaning("任务编号")
    state: str = meaning("任务状态，刚受理时为 queued")
    status_url: str = meaning("查询任务状态的地址")


def responses_for(*items: Contract[Any, Any]) -> dict[int | str, dict[str, Any]]:
    codes: dict[int, list[str]] = {STATUS[kind]: [KIND_TEXT[kind]] for kind in COMMON}
    for item in items:
        for error in item.errors:
            codes.setdefault(STATUS[error.kind], []).append(f"{error.code}：{error.message}")
    return {
        status: {"model": ErrorReply, "description": "；".join(texts)}
        for status, texts in sorted(codes.items())
    }
