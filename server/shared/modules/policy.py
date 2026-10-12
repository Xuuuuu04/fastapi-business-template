"""
包类型和操作效果共同约束真实依赖，流程状态可以持久化，领域数据仍有唯一所有者。
"""

from collections.abc import Sequence
from typing import Any, get_args

from pydantic import BaseModel

from shared.flow.flow import Flow
from shared.modules.contract import Contract
from shared.modules.module import Module


# 明确查询不能保存或登记任务，能力包跨域写入必须经流程编排。
def check_policy(modules: Sequence[Module]) -> list[str]:
    provided = {operation: module for module in modules for operation in module.provides}
    names = {module.name for module in modules}
    problems = []
    for module in modules:
        problems += provider_problems(module)
        problems += [
            issue
            for plan in module.jobs
            if plan.revalidate is not None
            for issue in dependency_problems(module, plan.contract, plan.revalidate)
        ]
        if module.kind not in (None, "capability", "workflow"):
            problems.append(f"模块 {module.name} 的kind无效")
        unknown = sorted(
            name for name in module.read_dependencies if name not in names or name == module.name
        )
        if unknown:
            problems.append(f"模块 {module.name} 的只读依赖未登记：{'、'.join(unknown)}")
        for operation, flow in module.provides.items():
            if not isinstance(flow, Flow):
                continue
            if module.kind and operation.effect is None:
                problems.append(f"操作 {operation.name} 必须明确声明query或command")
            if operation.effect == "query" and any(
                step.saves
                or step.later
                or step.providers
                or any(e.effect == "write" for e in step.endpoints)
                for step in flow.steps
            ):
                problems.append(f"查询操作 {operation.name} 不能保存业务数据或登记任务")
            targets = {target for part in flow.steps for target in (*part.uses, *part.later)}
            problems += [
                issue
                for target in targets
                if target in provided
                for issue in dependency_problems(module, operation, target)
            ]
            if module.kind:
                problems += data_problems(module, operation, flow.work)
    return problems


# 供应商范围与模块声明一致，错误流程由既有流程检查报告，不在这里重复解析。
def provider_problems(module: Module) -> list[str]:
    for spec in module.providers:
        spec.validate()
    return [
        f"步骤 {part.source} 的外部效果未在Module.providers登记"
        for flow in module.provides.values()
        if isinstance(flow, Flow)
        for part in flow.steps
        if any(spec not in module.providers for spec in part.providers)
    ]


# 声明只读依赖不能被后来的写操作悄悄替换。
def dependency_problems(module: Module, operation: Contract, target: Contract) -> list[str]:
    if operation.effect == "query" and target.effect != "query":
        return [f"查询 {operation.name} 不能调用写入或效果未知的操作 {target.name}"]
    if target.module == module.name:
        return []
    if module.kind != "capability":
        return []
    if target.effect != "query":
        return [f"能力包 {module.name} 跨域写入 {target.name}，请移到流程包"]
    if target.module not in module.read_dependencies:
        return [f"能力包 {module.name} 需要在read_dependencies声明只读依赖 {target.module}"]
    return []


# 原始接口数据只能在明确的边界模型里使用，领域契约不能长期靠Any分发。
def data_problems(module: Module, operation: Contract, work: type[BaseModel]) -> list[str]:
    problems = []
    for model in (operation.input, operation.output, work):
        pending = [model]
        seen = set()
        while pending:
            current = pending.pop()
            if current in seen or current in module.boundary_data:
                continue
            seen.add(current)
            for name, field in current.model_fields.items():
                types = nested_types(field.annotation)
                if Any in types or field.annotation in (dict, list):
                    problems.append(
                        f"操作 {operation.name} 的字段 {current.__name__}.{name} 缺少明确类型"
                    )
                pending.extend(t for t in types if isinstance(t, type) and issubclass(t, BaseModel))
    return problems


# 联合、集合与嵌套模型使用同一类型展开，不执行验证器或业务代码。
def nested_types(annotation: Any) -> list[Any]:
    return [annotation, *(value for part in get_args(annotation) for value in nested_types(part))]
