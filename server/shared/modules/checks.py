import inspect
import re
from collections.abc import Sequence
from typing import Any

from shared.access.caller import PUBLIC, SIGNED_IN
from shared.data.fields import check_notes
from shared.db.budget import check_budget
from shared.errors.kinds import BusinessError
from shared.flow.checks import check_flow
from shared.flow.flow import Flow
from shared.flow.step import Step
from shared.jobs.checks import check_jobs
from shared.model_calls.prompt import load_prompt
from shared.modules.aliases import check_aliases
from shared.modules.call_order import check_call_order
from shared.modules.contract import Contract
from shared.modules.identity import check_identity
from shared.modules.module import STORE_PARAMS, Module
from shared.modules.policy import check_policy
from shared.remote_calls.checks import check_endpoints

NAME = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
Provided = dict[Contract[Any, Any], Module]


def check_catalog(modules: Sequence[Module]) -> list[str]:
    problems = check_names(modules) + check_aliases(modules)
    problems += check_identity(modules)
    problems += check_endpoints(modules)
    provided: Provided = {}
    for module in modules:
        for item in module.provides:
            if item in provided:
                problems.append(f"操作 {item.name} 被多个模块提供")
            provided[item] = module
    for module in modules:
        problems += check_module(module)
    problems += check_uses(modules, provided)
    problems += check_cycles(modules, provided)
    problems += check_call_order({item: module.provides[item] for item, module in provided.items()})
    problems += check_error_codes(provided)
    problems += check_policy(modules)
    return problems


def check_names(modules: Sequence[Module]) -> list[str]:
    problems = []
    names = [module.name for module in modules]
    for name in sorted({name for name in names if names.count(name) > 1}):
        problems.append(f"模块名 {name} 重复登记")
    contracts = [item.name for module in modules for item in module.provides]
    for name in sorted({name for name in contracts if contracts.count(name) > 1}):
        problems.append(f"操作名 {name} 重复")
    for module in modules:
        if not NAME.match(module.name):
            problems.append(f"模块名 {module.name} 只能用小写字母、数字和下划线")
        for item in module.provides:
            parts = item.name.split(".")
            if len(parts) != 2 or not all(NAME.match(part) for part in parts):
                problems.append(f"操作名 {item.name} 必须写成“模块名.操作名”，全部小写")
    return problems


def check_module(module: Module) -> list[str]:
    problems = []
    for item, flow in module.provides.items():
        problems += check_contract(module, item, flow)
    for table in module.tables:
        if not table.name.startswith(f"{module.name}_"):
            problems.append(f"模块 {module.name} 的表 {table.name} 必须以 {module.name}_ 开头")
    problems += check_store(module)
    problems += check_prompts(module)
    problems += check_jobs(module)
    return problems


def check_store(module: Module) -> list[str]:
    if module.store is None:
        return []
    names = list(inspect.signature(module.store).parameters)
    place = f"模块 {module.name} 的存储实现 {getattr(module.store, '__name__', module.store)}"
    problems = [
        f"{place} 有不认识的构造参数 {name}，可用的参数名：{'、'.join(STORE_PARAMS)}"
        for name in names
        if name not in STORE_PARAMS
    ]
    if "remote" in names and not module.remotes:
        problems.append(f"{place} 使用 remote 参数，但模块没有在 remotes 中声明外部系统")
    return problems


def check_contract(module: Module, item: Contract[Any, Any], flow: Flow) -> list[str]:
    problems = []
    if item.module != module.name:
        problems.append(
            f"操作 {item.name} 登记在模块 {module.name} 中，名称前缀必须是 {module.name}."
        )
    if item.access not in (PUBLIC, SIGNED_IN) and not item.access.startswith(f"{module.name}."):
        problems.append(
            f"操作 {item.name} 的权限 {item.access} "
            f"必须是 public、signed_in 或以 {module.name}. 开头"
        )
    if not isinstance(flow, Flow):
        return [*problems, f"操作 {item.name} 对应的实现必须是 Flow"]
    problems += check_flow(flow, item, module.store is not None, module.prompts, module.remotes)
    problems += check_budget(item.query_budget, item.name)
    problems += check_notes(item.input, f"操作 {item.name} 的输入")
    problems += check_notes(item.output, f"操作 {item.name} 的输出")
    for error in item.errors:
        if not (issubclass(error, BusinessError) and error.code and error.message):
            problems.append(f"操作 {item.name} 声明的错误 {error.__name__} 必须写 code 和 message")
    return problems


def check_prompts(module: Module) -> list[str]:
    problems = []
    names = [item.name for item in module.prompts]
    for name in sorted({name for name in names if names.count(name) > 1}):
        problems.append(f"模块 {module.name} 的提示词 {name} 重复")
    for item in module.prompts:
        try:
            load_prompt(item)
        except (OSError, ValueError) as error:
            problems.append(f"模块 {module.name} 的提示词“{item.title}”无法读取：{error}")
    return problems


def check_uses(modules: Sequence[Module], provided: Provided) -> list[str]:
    problems = []
    problems += [
        f"任务 {plan.contract.name} 的执行前查询未登记"
        for module in modules
        for plan in module.jobs
        if plan.revalidate is not None and plan.revalidate not in provided
    ]
    planned = {plan.contract for module in modules for plan in module.jobs}
    for module, item in steps_of(modules):
        place = f"模块 {module.name} 的步骤“{item.title}”"
        problems += [
            f"{place} 调用了 {used.name}，但提供它的模块没有登记或已关闭"
            for used in item.uses
            if used not in provided
        ]
        problems += [
            f"{place} 登记的任务 {later.name} 没有在任何模块的 jobs 中声明"
            for later in item.later
            if later not in planned
        ]
    return problems


def steps_of(modules: Sequence[Module]) -> list[tuple[Module, Step]]:
    return [
        (module, item)
        for module in modules
        for flow in module.provides.values()
        if isinstance(flow, Flow)
        for item in flow.steps
    ]


def check_cycles(modules: Sequence[Module], provided: Provided) -> list[str]:
    calls = {item: used_by(flow) for module in modules for item, flow in module.provides.items()}
    for module in modules:
        for plan in module.jobs:
            if plan.revalidate is not None:
                calls.setdefault(plan.contract, set()).add(plan.revalidate)
    problems = [
        f"操作之间存在循环调用：{' → '.join(item.name for item in loop)}"
        for loop in find_loops(calls)
    ]
    links: dict[str, set[str]] = {module.name: set() for module in modules}
    for item, targets in calls.items():
        for target in targets:
            if target in provided and target.module != item.module:
                links[item.module].add(target.module)
    problems += [f"模块之间存在循环依赖：{' → '.join(loop)}" for loop in find_loops(links)]
    return problems


def used_by(flow: Flow) -> set[Contract[Any, Any]]:
    if not isinstance(flow, Flow):
        return set()
    return {used for item in flow.steps for used in item.uses}


def find_loops[Node](graph: dict[Node, set[Node]]) -> list[list[Node]]:
    loops: list[list[Node]] = []
    done: set[Node] = set()

    def visit(node: Node, path: list[Node]) -> None:
        if node in path:
            loops.append([*path[path.index(node) :], node])
            return
        if node in done:
            return
        for target in graph.get(node, set()):
            visit(target, [*path, node])
        done.add(node)

    for node in list(graph):
        visit(node, [])
    return loops


def check_error_codes(provided: Provided) -> list[str]:
    owners: dict[str, type[BusinessError]] = {}
    problems = []
    for item in provided:
        for error in item.errors:
            known = owners.setdefault(error.code, error)
            if known is not error:
                problems.append(
                    f"错误码 {error.code} 同时用于 {known.__name__} 和 {error.__name__}"
                )
    return problems
