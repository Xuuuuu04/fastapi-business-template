import keyword
import re
from typing import Any, Literal

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


class SkeletonField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    meaning: str = Field(min_length=1, max_length=500)


class SkeletonCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: str
    input: dict[str, str]
    case: str


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


class SkeletonPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$")
    title: str = Field(min_length=1, max_length=100)
    kind: Literal["capability", "workflow"]
    operations: list[SkeletonOperation] = Field(min_length=1)


class SkeletonBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    packages: list[SkeletonPackage] = Field(min_length=1)

    def validate_links(self) -> None:
        if len({package.name for package in self.packages}) != len(self.packages):
            raise ValueError("骨架业务包名称重复：" + ", ".join(p.name for p in self.packages))
        operations: dict[str, SkeletonOperation] = {}
        for package in self.packages:
            collect_operations(package, operations)
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


def collect_operations(package: SkeletonPackage, operations: dict[str, SkeletonOperation]) -> None:
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


def validate_identity(package: str, operation: SkeletonOperation) -> None:
    identity = package + "." + operation.name
    if operation.access not in {"public", "signed_in"} and not (
        operation.access.startswith(package + ".")
        and re.fullmatch(NAME, operation.access[len(package) + 1 :])
    ):
        raise ValueError(
            f"{identity}：权限 {operation.access!r} 必须是 public、signed_in "
            f"或以 {package}. 开头的权限名"
        )
    if len(set(operation.cases)) != len(operation.cases) or any(
        not re.fullmatch(re.escape(package) + r"\.R-\d+-C\d+", case) for case in operation.cases
    ):
        raise ValueError(f"{identity}：样例编号无效或重复：{operation.cases}")


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


def validate_fields(operation: SkeletonOperation) -> None:
    for fields in (operation.input, operation.output):
        if not fields:
            raise ValueError("骨架需要明确的输入与输出字段")
        for name, field in fields.items():
            if (
                not re.fullmatch(NAME, name)
                or keyword.iskeyword(name)
                or name.startswith(("_", "model_"))
                or name == "result"
                or field.type not in TYPES
            ):
                raise ValueError(f"字段 {name} 的名称或类型 {field.type!r} 不支持")


def call_field(operation: str) -> str:
    return operation.replace(".", "_")


def reference_type(reference: str, available: dict[str, dict[str, SkeletonField]]) -> str:
    source, separator, name = reference.rpartition(".")
    if not separator or source not in available or name not in available[source]:
        sources = "、".join(f"{item}.字段" for item in available)
        raise ValueError(f"骨架字段来源未定义或属于未来阶段：{reference}；可用来源：{sources}")
    return available[source][name].type


def validate_calls(operation: SkeletonOperation, operations: dict[str, SkeletonOperation]) -> None:
    available = {"input": operation.input}
    if len({call.operation for call in operation.calls}) != len(operation.calls):
        raise ValueError("同一操作重复调用需要独立的位置声明，不能使用本短骨架")
    fields = set(operation.input)
    for call in operation.calls:
        target = operations.get(call.operation)
        if target is None or call.case not in target.cases:
            raise ValueError(f"调用 {call.operation} 或独立样例 {call.case} 未定义")
        if operation.effect == "query" and target.effect == "command":
            raise ValueError("查询骨架不能连接对外写入操作")
        validate_mapping(call.input, target.input, available)
        if call_field(call.operation) in fields:
            raise ValueError(
                f"调用 {call.operation} 的产出字段 {call_field(call.operation)} "
                "与输入字段或其他调用重名"
            )
        fields.add(call_field(call.operation))
        available[call.operation] = target.output
    if operation.calls:
        validate_mapping(operation.returns, operation.output, available)
    elif operation.returns:
        raise ValueError("模拟骨架不能包含根据预期取值生成的返回映射")


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


class CaseFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*\.R-\d+-C\d+$")
    input: dict[str, Any]
    initial: dict[str, Any]
    expected: dict[str, Any]
    observations: list[dict[str, Any]] = Field(default_factory=list)
    database: dict[str, Any] = Field(default_factory=dict)
    effects: dict[str, Any] = Field(default_factory=dict)
    assertions: list[str] = Field(min_length=1)
    tests: list[str] = Field(min_length=1)
