import inspect
import re
from dataclasses import dataclass, field
from typing import Any, Literal, get_args

from pydantic import BaseModel, ValidationError

from shared.data.fields import check_notes
from shared.data.models import Data
from shared.errors.framework import RemoteOutputInvalid, RemoteResultUnknown
from shared.records.models import RemoteCallRecord
from shared.remote_calls.routing import routing_problems, validation_shape


@dataclass(frozen=True, eq=False)
class Endpoint[In: Data, Out: Data]:
    name: str
    method: str
    path: str
    input: type[In]
    output: type[Out]
    effect: Literal["read", "write"]
    unknown_on: tuple[int, ...] = ()
    accepted_statuses: tuple[int, ...] = ()
    source: str = field(init=False, default="")
    path_fields: tuple[str, ...] = ()
    query_fields: tuple[str, ...] = ()
    body_fields: tuple[str, ...] | None = None
    file_fields: tuple[str, ...] = ()
    max_upload_bytes: int = 16_000_000
    receipt_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "method", self.method.upper())
        frame = inspect.currentframe()
        try:
            caller = frame.f_back.f_back if frame and frame.f_back else None
            if caller:
                object.__setattr__(self, "source", caller.f_globals.get("__name__", ""))
        finally:
            del frame

    def shape(self) -> dict[str, Any]:
        return dict(
            name=self.name,
            source=self.source,
            method=self.method,
            path=self.path,
            effect=self.effect,
            input=self.input.model_json_schema(),
            output=self.output.model_json_schema(),
            unknown_on=self.unknown_on,
            accepted_statuses=self.accepted_statuses,
            path_fields=self.path_fields,
            query_fields=self.query_fields,
            body_fields=self.body_fields,
            file_fields=self.file_fields,
            max_upload_bytes=self.max_upload_bytes,
            validation=validation_shape(self),
        )


@dataclass(frozen=True)
class EndpointReply[Out: Data]:
    status: int
    data: Out


def validate_output[In: Data, Out: Data](
    endpoint: Endpoint[In, Out], raw: Any, record: RemoteCallRecord
) -> Out:
    try:
        result = endpoint.output.model_validate(raw)
        missing = {
            name
            for name in endpoint.receipt_fields
            if name not in result.model_fields_set or getattr(result, name) is None
        }
        if missing:
            record.fields = {name: "响应缺少用于确认结果的关键字段" for name in missing}
            if endpoint.effect == "write" and record.outcome == "ok":
                record.outcome = "unknown"
                raise RemoteResultUnknown(
                    "响应中缺少用于确认结果的关键字段，写入结果需要确认"
                ) from None
            raise RemoteOutputInvalid("响应中缺少用于确认结果的关键字段") from None
        return result
    except ValidationError as error:
        fields = {}
        known = field_names(endpoint.output)
        for issue in error.errors(include_url=False, include_input=False)[:50]:
            path = ".".join(
                str(part) if isinstance(part, int) or part in known else "$key"
                for part in issue["loc"]
            )
            if issue["type"] == "extra_forbidden":
                path = "$extra"
            if len(path.encode("utf-8")) <= 200:
                fields[path or "$"] = f"不符合接口字段约定（{issue['type']}）"
        record.fields = fields
        record.error = f"外部接口 {endpoint.name} 响应字段校验失败"
        if endpoint.effect == "write" and record.outcome == "ok":
            record.outcome = "unknown"
            raise RemoteResultUnknown(record.error + "，写入结果需要确认", fields=fields) from None
        raise RemoteOutputInvalid(record.error, fields=fields) from None


def endpoint_problems(endpoint: Endpoint[Any, Any]) -> list[str]:
    place = f"外部接口 {endpoint.name}"
    problems = []
    if not re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+", endpoint.name):
        problems.append(f"{place} 名称必须是系统名.接口名，全部小写")
    if endpoint.method not in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
        problems.append(f"{place} HTTP方法不支持")
    if (
        not endpoint.path.startswith("/")
        or endpoint.path.startswith("//")
        or "://" in endpoint.path
    ):
        problems.append(f"{place} 路径必须是声明的站内绝对路径")
    if endpoint.effect not in ("read", "write"):
        problems.append(f"{place} effect只能是read或write")
    for model in (endpoint.input, endpoint.output):
        if not isinstance(model, type) or not issubclass(model, Data):
            problems.append(f"{place} input/output必须是Data子类")
        else:
            problems += check_notes(model, place)
    if any(type(code) is not int or not 100 <= code <= 599 for code in endpoint.unknown_on):
        problems.append(f"{place} unknown_on必须是HTTP状态码")
    if any(
        type(code) is not int or not 400 <= code < 500 or code in (408, 499)
        for code in endpoint.accepted_statuses
    ):
        problems.append(f"{place} accepted_statuses只允许除408/499外的4xx")
    if set(endpoint.unknown_on) & set(endpoint.accepted_statuses):
        problems.append(f"{place} 待确认状态不能同时声明为确定拒绝")
    problems += routing_problems(endpoint)
    return problems


def field_names(model: type[BaseModel]) -> set[str]:
    names: set[str] = set()
    pending: list[Any] = [model]
    seen: set[type[BaseModel]] = set()
    while pending:
        current = pending.pop()
        if not isinstance(current, type) or not issubclass(current, BaseModel):
            pending.extend(get_args(current))
            continue
        if current in seen:
            continue
        seen.add(current)
        for name, info in current.model_fields.items():
            names.add(name)
            names.update(
                alias for alias in (info.alias, info.validation_alias) if isinstance(alias, str)
            )
            pending.append(info.annotation)
    return names
