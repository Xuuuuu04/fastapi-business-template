import re
from typing import TYPE_CHECKING, Any, get_args
from urllib.parse import quote

from pydantic import BaseModel

from shared.errors.framework import StepRuleBroken

if TYPE_CHECKING:
    from shared.remote_calls.endpoint import Endpoint


def routing_problems(endpoint: "Endpoint") -> list[str]:
    fields = set(endpoint.input.model_fields)
    path = re.findall(r"\{([a-z][a-z0-9_]*)\}", endpoint.path)
    declared = [*endpoint.path_fields, *endpoint.query_fields, *(endpoint.body_fields or ())]
    problems = []
    if set(path) != set(endpoint.path_fields) or len(path) != len(set(path)):
        problems.append(f"外部接口 {endpoint.name} 的路径参数与path_fields不一致")
    if "{" in re.sub(r"\{[a-z][a-z0-9_]*\}", "", endpoint.path) or "}" in re.sub(
        r"\{[a-z][a-z0-9_]*\}", "", endpoint.path
    ):
        problems.append(f"外部接口 {endpoint.name} 的路径模板无效")
    if len(declared) != len(set(declared)) or set(declared) - fields:
        problems.append(f"外部接口 {endpoint.name} 的输入位置重复或字段未声明")
    if endpoint.body_fields is not None and set(declared) != fields:
        problems.append(f"外部接口 {endpoint.name} 有未分配到传输位置的字段")
    if len(endpoint.file_fields) != len(set(endpoint.file_fields)) or any(
        not re.fullmatch(r"[a-z][a-z0-9_]*", name) for name in endpoint.file_fields
    ):
        problems.append(f"外部接口 {endpoint.name} 的文件字段无效")
    if endpoint.file_fields and endpoint.method in {"GET", "HEAD"}:
        problems.append(f"外部接口 {endpoint.name} 的读取方法不能携带文件正文")
    if endpoint.max_upload_bytes < 1:
        problems.append(f"外部接口 {endpoint.name} 的文件上限必须为正数")
    if any(name not in endpoint.output.model_fields for name in endpoint.receipt_fields):
        problems.append(f"外部接口 {endpoint.name} 用于确认结果的关键字段未在 output 中声明")
    return problems


def render_path(template: str, payload: dict[str, Any], fields: tuple[str, ...]) -> str:
    path = template
    for name in fields:
        value = payload[name]
        if type(value) not in {str, int} or str(value) in {"", ".", ".."} or len(str(value)) > 512:
            raise StepRuleBroken(
                f"外部接口的路径参数 {name} 必须是整数或字符串，最多 512 个字符，"
                "且不能是空文本、. 或 .."
            )
        path = path.replace("{" + name + "}", quote(str(value), safe=""))
    return path


def validation_shape(endpoint: "Endpoint") -> dict[str, Any]:
    model = endpoint.output
    return dict(
        validated_fields=list(model.model_fields),
        extension_policy=model.model_config.get("extra", "ignore"),
        receipt_fields=list(endpoint.receipt_fields),
        complete=typed_output(model),
    )


def typed_output(model: type[BaseModel]) -> bool:
    pending: list[Any] = [model]
    seen = set()
    while pending:
        current = pending.pop()
        if current is Any or current in (dict, list, set, tuple):
            return False
        if isinstance(current, type) and issubclass(current, BaseModel):
            if current in seen:
                continue
            seen.add(current)
            if not current.model_fields or current.model_config.get("extra") != "forbid":
                return False
            pending.extend(info.annotation for info in current.model_fields.values())
        else:
            pending.extend(get_args(current))
    return True
