"""
骨架只接受明确的数据字段、权限和调用映射；不读取确认预期来生成正式实现。
"""

import keyword
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

NAME = r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$"
TYPES = {
    "str",
    "int",
    "float",
    "bool",
    "list[str]",
    "list[int]",
    "dict[str, str]",
    "dict[str, int]",
}


# 公开字段描述不包含业务样例取值。
class SkeletonField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    meaning: str = Field(min_length=1, max_length=500)


# 每个参数和最终结果都显式指定来源，不猜相同名字字段的业务含义。
class SkeletonCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: str
    input: dict[str, str]
    case: str


# 可用骨架或真实连接步骤，但权限与效果必须由声明提供。
class SkeletonOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=NAME)
    title: str = Field(min_length=1, max_length=100)
    access: str = Field(min_length=1)
    effect: Literal["query", "command"]
    input: dict[str, SkeletonField]
    output: dict[str, SkeletonField]
    cases: list[str] = Field(min_length=1)
    calls: list[SkeletonCall] = Field(default_factory=list)
    returns: dict[str, str] = Field(default_factory=dict)


# 新业务包从完整声明生成，已有业务不会被覆写或归类。
class SkeletonPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$")
    title: str = Field(min_length=1, max_length=100)
    kind: Literal["capability", "workflow"]
    operations: list[SkeletonOperation] = Field(min_length=1)


# 一批新包的调用关系必须完整、有序且无循环。
class SkeletonBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    line: str = Field(min_length=1, max_length=100)
    packages: list[SkeletonPackage] = Field(min_length=1)

    # 生成文件之前核对全部名称、字段和跨包连接。
    def validate_links(self) -> None:
        if len({package.name for package in self.packages}) != len(self.packages):
            raise ValueError("骨架业务包名称重复：" + ", ".join(p.name for p in self.packages))
        operations = {}
        for package in self.packages:
            cases: set[str] = set()
            for operation in package.operations:
                identity = package.name + "." + operation.name
                repeated = cases.intersection(operation.cases)
                if repeated:
                    raise ValueError(f"{identity}：不同操作需要独立样例编号，重复 {sorted(repeated)}")
                cases.update(operation.cases)
                if identity in operations or keyword.iskeyword(operation.name):
                    raise ValueError(f"{identity}：骨架操作名称重复或使用保留字")
                operations[identity] = operation
                validate_identity(package.name, operation)
                try:
                    validate_fields(operation)
                except ValueError as error:
                    raise ValueError(f"{identity}：{error}") from error
        graph = {}
        for package in self.packages:
            for operation in package.operations:
                identity = package.name + "." + operation.name
                if operation.calls and package.kind != "workflow":
                    raise ValueError(f"{identity}：连接多包的骨架必须明确声明为流程包")
                try:
                    validate_calls(operation, operations)
                except ValueError as error:
                    raise ValueError(f"{identity}：{error}") from error
                graph[package.name + "." + operation.name] = [c.operation for c in operation.calls]
        check_cycles(graph)


# 核对单操作的权限命名与独立样例编号，并报告完整操作名。
def validate_identity(package: str, operation: SkeletonOperation) -> None:
    identity = package + "." + operation.name
    if operation.access not in {"public", "signed_in"} and not (
        operation.access.startswith(package + ".")
        and re.fullmatch(NAME, operation.access[len(package) + 1:])
    ):
        raise ValueError(
            f"{identity}：权限 {operation.access!r} 必须是 public、signed_in "
            f"或以 {package}. 开头的权限名"
        )
    if len(set(operation.cases)) != len(operation.cases) or any(
        not re.fullmatch(re.escape(package) + r"\.R-\d+-C\d+", case)
        for case in operation.cases
    ):
        raise ValueError(f"{identity}：样例编号无效或重复：{operation.cases}")


# 调用图独立核对循环，不能靠生成文件顺序规避循环依赖。
def check_cycles(graph: dict[str, list[str]]) -> None:
    for identity in graph:
        pending, seen = list(graph[identity]), set()
        while pending:
            target = pending.pop()
            if target == identity:
                raise ValueError(f"{identity}：骨架公开调用形成循环")
            if target not in seen:
                seen.add(target)
                pending.extend(graph[target])


# 保留框架中间字段名，类型采用固定白名单，不执行外来的类型表达式。
def validate_fields(operation: SkeletonOperation) -> None:
    for fields in (operation.input, operation.output):
        if not fields:
            raise ValueError("骨架需要明确的输入与输出字段")
        for name, field in fields.items():
            if (
                not re.fullmatch(NAME, name)
                or keyword.iskeyword(name)
                or name.startswith(("_", "model_", "phase_"))
                or name == "result"
                or field.type not in TYPES
            ):
                raise ValueError(f"字段 {name} 的名称或类型 {field.type!r} 不支持")


# 字段引用只能来自原始输入或已经运行的步骤产出。
def reference_type(reference: str, available: dict[str, dict[str, SkeletonField]]) -> str:
    source, separator, name = reference.partition(".")
    if not separator or source not in available or name not in available[source]:
        raise ValueError(f"骨架字段来源未定义或属于未来阶段：{reference}")
    return available[source][name].type


# 每个调用的完整入参和最后输出都逐项核对类型；重复同位置调用不能伪造观察成功。
def validate_calls(operation: SkeletonOperation, operations: dict[str, SkeletonOperation]) -> None:
    available = {"input": operation.input}
    if len({call.operation for call in operation.calls}) != len(operation.calls):
        raise ValueError("同一操作重复调用需要独立的位置声明，不能使用本短骨架")
    for number, call in enumerate(operation.calls, 1):
        target = operations.get(call.operation)
        if target is None or call.case not in target.cases:
            raise ValueError(f"调用 {call.operation} 或独立样例 {call.case} 未定义")
        if operation.effect == "query" and target.effect == "command":
            raise ValueError("查询骨架不能连接对外写入操作")
        validate_mapping(call.input, target.input, available)
        available[f"phase_{number}"] = target.output
    if operation.calls:
        validate_mapping(operation.returns, operation.output, available)
    elif operation.returns:
        raise ValueError("模拟骨架不能包含根据预期取值生成的返回映射")


# 参数与产出采用同一完整映射约定，字段没有明确来源时不能靠名字推断。
def validate_mapping(
    values: dict[str, str],
    target: dict[str, SkeletonField],
    available: dict[str, dict[str, SkeletonField]],
) -> None:
    if set(values) != set(target):
        raise ValueError(
            f"骨架映射缺少字段 {sorted(set(target) - set(values))}，"
            f"多余字段 {sorted(set(values) - set(target))}"
        )
    for name, reference in values.items():
        if reference_type(reference, available) != target[name].type:
            raise ValueError(f"字段 {name} 来源 {reference} 的类型与 {target[name].type} 不一致")
