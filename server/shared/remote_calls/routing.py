"""
协议声明把输入分配到路径、查询、正文和文件，各位置均可追踪，不允许未声明文件字段。
"""

import re
from typing import TYPE_CHECKING, Any, get_args
from urllib.parse import quote

from pydantic import BaseModel

from shared.errors.framework import StepRuleBroken

if TYPE_CHECKING:
    from shared.remote_calls.endpoint import Endpoint


# 参数名使用数据模型字段名，序列化后采用模型自己的上游别名。
def routing_problems(endpoint: "Endpoint") -> list[str]:
    fields = set(endpoint.input.model_fields)
    path = re.findall(r"\{([a-z][a-z0-9_]*)\}", endpoint.path)
    declared = [*endpoint.path_fields, *endpoint.query_fields, *(endpoint.body_fields or ())]
    problems = []
    if set(path) != set(endpoint.path_fields) or len(path) != len(set(path)):
        problems.append(f"上游接口 {endpoint.name} 的路径参数与path_fields不一致")
    if "{" in re.sub(r"\{[a-z][a-z0-9_]*\}", "", endpoint.path) or "}" in re.sub(
        r"\{[a-z][a-z0-9_]*\}", "", endpoint.path
    ):
        problems.append(f"上游接口 {endpoint.name} 的路径模板无效")
    if len(declared) != len(set(declared)) or set(declared) - fields:
        problems.append(f"上游接口 {endpoint.name} 的输入位置重复或字段未声明")
    if endpoint.body_fields is not None and set(declared) != fields:
        problems.append(f"上游接口 {endpoint.name} 有未分配到传输位置的字段")
    if len(endpoint.file_fields) != len(set(endpoint.file_fields)) or any(
        not re.fullmatch(r"[a-z][a-z0-9_]*", name) for name in endpoint.file_fields
    ):
        problems.append(f"上游接口 {endpoint.name} 的文件字段无效")
    if endpoint.file_fields and endpoint.method in {"GET", "HEAD"}:
        problems.append(f"上游接口 {endpoint.name} 的读取方法不能携带文件正文")
    if endpoint.max_upload_bytes < 1:
        problems.append(f"上游接口 {endpoint.name} 的文件上限必须为正数")
    if any(name not in endpoint.output.model_fields for name in endpoint.receipt_fields):
        problems.append(f"上游接口 {endpoint.name} 的关键回执字段未在输出声明")
    return problems


# 字段值不能变成路径结构，空值和目录跳转段在发送前拒绝。
def render_path(template: str, payload: dict[str, Any], fields: tuple[str, ...]) -> str:
    path = template
    for name in fields:
        value = payload[name]
        if type(value) not in {str, int} or str(value) in {"", ".", ".."} or len(str(value)) > 512:
            raise StepRuleBroken(f"上游路径参数 {name} 必须是有界字符串或整数")
        path = path.replace("{" + name + "}", quote(str(value), safe=""))
    return path


# 兼容协议仍明确展示实际校验范围，空模型和任意扩展不能显示为完整协议验证。
def validation_shape(endpoint: "Endpoint") -> dict[str, Any]:
    model = endpoint.output
    return dict(
        validated_fields=list(model.model_fields),
        extension_policy=model.model_config.get("extra", "ignore"),
        receipt_fields=list(endpoint.receipt_fields),
        complete=typed_output(model),
    )


# 嵌套Any和允许未知扩展的模型同样属于部分验证，不只检查最外层字段数量。
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
