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
from shared.pipelines.plan import stages_of
from shared.pipelines.registration import check_pipelines, expand
from shared.remote_calls.checks import check_endpoints


@dataclass(frozen=True, eq=False)
class Binding:
    contract: Contract[Any, Any]
    module: Module
    flow: Flow
    types: FieldTypes


class Catalog:
    def __init__(self, modules: Sequence[Module], *, strict_endpoints: bool = False) -> None:
        pipeline_problems = check_pipelines(modules)
        if pipeline_problems:
            raise DeclarationError(pipeline_problems)
        modules = expand(modules)
        problems = pipeline_problems + check_catalog(modules)
        if strict_endpoints:
            problems += check_endpoints(modules, strict=True)
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

    def binding(self, item: Contract[Any, Any]) -> Binding:
        found = self.bindings.get(item)
        if found is None:
            raise StepRuleBroken(f"操作 {item.name} 没有登记，或者提供它的模块没有启用")
        return found

    def find(self, name: str) -> Binding | None:
        return self.by_name.get(name)

    def plan(self, name: str) -> JobPlan | None:
        return self.plans.get(name)

    def prompts(self) -> list[Prompt]:
        return [item for module in self.modules.values() for item in module.prompts]

    def links(self) -> dict[str, dict[str, list[str]]]:
        result: dict[str, dict[str, list[str]]] = {name: {} for name in self.modules}
        for source, target, title in self.edges():
            titles = result[source].setdefault(target, [])
            if title not in titles:
                titles.append(title)
        return result

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
            for stage in stages_of(pipeline)
            if stage.operation.module != module.name
        ]
        edges += [
            (module.name, plan.revalidate.module, f"执行前查询：{plan.revalidate.title}")
            for module in self.modules.values()
            for plan in module.jobs
            if plan.revalidate is not None and plan.revalidate.module != module.name
        ]
        edges += [
            (module.name, endpoint.source.split(".")[1], f"上游协议：{endpoint.name}")
            for module in self.modules.values()
            for endpoint in module.endpoints
            if endpoint.source.startswith("service.")
            and endpoint.source.split(".")[1] in self.modules
            and endpoint.source.split(".")[1] != module.name
        ]
        return edges
