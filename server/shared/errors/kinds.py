from enum import StrEnum
from typing import ClassVar


class Kind(StrEnum):
    INVALID = "invalid"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    NOT_SIGNED_IN = "not_signed_in"
    FORBIDDEN = "forbidden"
    TOO_MANY = "too_many"
    TEMPORARY = "temporary"
    TIMEOUT = "timeout"
    UNKNOWN_RESULT = "unknown_result"
    BROKEN = "broken"


KIND_TEXT = {
    Kind.INVALID: "输入不符合要求",
    Kind.NOT_FOUND: "要找的数据不存在",
    Kind.CONFLICT: "与现有数据冲突",
    Kind.NOT_SIGNED_IN: "没有提供有效身份",
    Kind.FORBIDDEN: "没有权限",
    Kind.TOO_MANY: "请求过多或排队已满",
    Kind.TEMPORARY: "暂时故障，可以稍后重试",
    Kind.TIMEOUT: "处理超时",
    Kind.UNKNOWN_RESULT: "结果尚不能确认",
    Kind.BROKEN: "程序与声明不一致，需要修改代码",
}

RETRY_KINDS = frozenset({Kind.TEMPORARY, Kind.TIMEOUT})


class BusinessError(Exception):
    code: ClassVar[str] = ""
    kind: ClassVar[Kind] = Kind.INVALID
    message: ClassVar[str] = ""

    def __init__(self, detail: str = "", *, fields: dict[str, str] | None = None) -> None:
        self.detail = detail or self.message
        self.fields = dict(fields or {})
        self.run_id = ""
        super().__init__(self.detail)
