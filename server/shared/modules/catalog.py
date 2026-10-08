"""
模块目录 Catalog：启动时检查全部模块声明，检查通过后固定下来，供执行器、接口、任务和文档共同使用。
检查不通过就抛出 DeclarationError，一次列出全部问题，服务不会带着错误的声明启动。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from shared.errors.framework import DeclarationError, StepRuleBroken
from shared.flow.flow import Flow
from shared.flow.view import FieldTypes
from shared.jobs.plan import JobPlan, Schedule
from shared.model_calls.prompt import Prompt
from shared.modules.checks import check_catalog
from shared.modules.contract import Contract
from shared.modules.digest import digest_of
from shared.modules.module import Module
from shared.pipelines.registration import check_pipelines, expand


# 一个公开操作与其模块、计算流程和字段说明之间的对应关系。
@dataclass(frozen=True, eq=False)
class Binding:
    contract: Contract[Any, Any]
    module: Module
    flow: Flow
    types: FieldTypes


# 统一保存模块和公开操作，启动时检查依赖与流程声明。
class Catalog:
    # 检查模块声明并建立查找表；有问题时一次列出全部问题。
    def __init__(self, modules: Sequence[Module]) -> None:
        pipeline_problems = check_pipelines(modules)
        if pipeline_problems:
            raise DeclarationError(pipeline_problems)
        modules = expand(modules)
        problems = pipeline_problems + check_catalog(modules)
        if problems:
            raise DeclarationError(problems)
        self.modules = {module.name: module for module in modules}
        self.pipelines = {p.name: p for module in modules for p in module.pipelines}
        self.pipeline_starts = {p.start.name: p for p in self.pipelines.values()}
        self.identity = next(
            (module.identity for module in modules if module.identity is not None), None
        )
        self.identity_header = next(
            (module.identity_header for module in modules if module.identity is not None), ""
        )
        self.identity_token = next(
            (module.identity_token for module in modules if module.identity is not None), "jwt"
        )
        self.bindings: dict[Contract[Any, Any], Binding] = {
            item: Binding(item, module, flow, FieldTypes(flow.work))
            for module in modules
            for item, flow in module.provides.items()
        }
        self.by_name = {item.name: binding for item, binding in self.bindings.items()}
        self.plans = {plan.contract.name: plan for module in modules for plan in module.jobs}
        self.schedules: list[Schedule] = [s for module in modules for s in module.schedules]
        self.digest = digest_of(modules)

    # 取得一个操作的实现；没有登记时报错。
    def binding(self, item: Contract[Any, Any]) -> Binding:
        found = self.bindings.get(item)
        if found is None:
            raise StepRuleBroken(f"操作 {item.name} 没有登记，或者提供它的模块没有启用")
        return found

    # 按操作名查找实现。
    def find(self, name: str) -> Binding | None:
        return self.by_name.get(name)

    # 按操作名查找任务声明。
    def plan(self, name: str) -> JobPlan | None:
        return self.plans.get(name)

    # 列出全部模块的提示词。
    def prompts(self) -> list[Prompt]:
        return [item for module in self.modules.values() for item in module.prompts]

    # 返回每个模块调用了哪些其他模块，以及经由哪些操作。
    def links(self) -> dict[str, dict[str, list[str]]]:
        result: dict[str, dict[str, list[str]]] = {name: {} for name in self.modules}
        for source, target, title in self.edges():
            titles = result[source].setdefault(target, [])
            if title not in titles:
                titles.append(title)
        return result

    # 列出跨模块调用的每一条边：调用方模块、被调用模块、被调用操作的名称。
    def edges(self) -> list[tuple[str, str, str]]:
        edges = [
            (
                binding.module.name,
                used.module,
                f"后台任务：{used.title}" if used in part.later else used.title,
            )
            for binding in self.bindings.values()
            for part in binding.flow.steps
            for used in (*part.uses, *part.later)
            if used.module != binding.module.name
        ]
        edges += [
            (module.name, stage.operation.module, f"流程阶段：{stage.operation.title}")
            for module in self.modules.values()
            for pipeline in module.pipelines
            for stage in pipeline.stages
            if stage.operation.module != module.name
        ]
        return edges
