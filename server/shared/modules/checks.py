"""
启动时检查全部模块声明，返回全部问题。
覆盖：名称格式与重复、操作归属与权限命名、流程声明、字段说明、表名归属、提示词文件、
存储实现的构造参数、任务与定时计划、跨模块调用是否已登记、操作之间和模块之间有没有循环调用。
"""

import inspect
import re
from collections.abc import Sequence
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from shared.access.caller import PUBLIC, SIGNED_IN
from shared.data.fields import check_notes
from shared.errors.kinds import BusinessError
from shared.flow.checks import check_flow
from shared.flow.flow import Flow
from shared.flow.step import Step
from shared.jobs.checks import check_segmented_jobs
from shared.model_calls.prompt import load_prompt
from shared.modules.contract import Contract
from shared.modules.module import STORE_PARAMS, Module

NAME = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
Provided = dict[Contract[Any, Any], Module]


# 检查全部模块声明。
def check_catalog(modules: Sequence[Module]) -> list[str]:
    problems = check_names(modules)
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
    problems += check_model_in_save(provided)
    problems += check_error_codes(provided)
    return problems


# 检查模块名和操作名的格式与唯一性。
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


# 检查单个模块：操作归属、权限、流程、表、提示词、任务。
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


# 存储实现的构造参数名决定框架注入什么，只能使用约定的名称。
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


# 检查一个操作约定及其流程。
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
    problems += check_notes(item.input, f"操作 {item.name} 的输入")
    problems += check_notes(item.output, f"操作 {item.name} 的输出")
    for error in item.errors:
        if not (issubclass(error, BusinessError) and error.code and error.message):
            problems.append(f"操作 {item.name} 声明的错误 {error.__name__} 必须写 code 和 message")
    return problems


# 检查提示词名称唯一、文件存在且格式正确。
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


# 检查后台任务和定时计划的声明。
def check_jobs(module: Module) -> list[str]:
    problems = []
    problems += check_segmented_jobs(module)
    planned = {plan.contract for plan in module.jobs}
    for plan in module.jobs:
        if plan.contract not in module.provides:
            problems.append(f"任务 {plan.contract.name} 不是模块 {module.name} 提供的操作")
        elif not plan.contract.entry:
            problems.append(
                f"任务 {plan.contract.name} 是内部操作（entry=False），不能作为任务运行"
            )
    for schedule in module.schedules:
        place = f"定时计划“{schedule.title}”"
        if schedule.contract not in planned:
            problems.append(f"{place} 的操作 {schedule.contract.name} 需要先在 jobs 中声明")
        if (schedule.every is None) == (schedule.daily_at is None):
            problems.append(f"{place} 必须且只能设置 every 或 daily_at 其中一个")
        if not isinstance(schedule.input, schedule.contract.input):
            problems.append(f"{place} 的输入类型必须是 {schedule.contract.input.__name__}")
        try:
            ZoneInfo(schedule.zone)
        except (ZoneInfoNotFoundError, ValueError):
            problems.append(f"{place} 的时区 {schedule.zone} 无法识别")
    return problems


# 检查步骤调用和登记的操作都由已启用的模块提供。
def check_uses(modules: Sequence[Module], provided: Provided) -> list[str]:
    problems = []
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


# 列出全部模块中的全部步骤。
def steps_of(modules: Sequence[Module]) -> list[tuple[Module, Step]]:
    return [
        (module, item)
        for module in modules
        for flow in module.provides.values()
        if isinstance(flow, Flow)
        for item in flow.steps
    ]


# 检查操作之间、模块之间没有循环调用。
def check_cycles(modules: Sequence[Module], provided: Provided) -> list[str]:
    calls = {item: used_by(flow) for module in modules for item, flow in module.provides.items()}
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


# 列出一个流程中所有步骤调用的操作。
def used_by(flow: Flow) -> set[Contract[Any, Any]]:
    if not isinstance(flow, Flow):
        return set()
    return {used for item in flow.steps for used in item.uses}


# 在有向图中找出循环，每个循环只报告一次。
def find_loops[Node](graph: dict[Node, set[Node]]) -> list[list[Node]]:
    loops: list[list[Node]] = []
    done: set[Node] = set()

    # 深度优先遍历，path 记录当前路径。
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


# 检查写入事务开始后，是否还调用了会用到大模型的操作。
def check_model_in_save(provided: Provided) -> list[str]:
    flows = {item: module.provides[item] for item, module in provided.items()}
    memo: dict[Contract[Any, Any], bool] = {}
    problems = []
    for item, flow in flows.items():
        saving = None
        for part in flow.steps if isinstance(flow, Flow) else ():
            if part.saves and saving is None:
                saving = part
            elif saving is not None and any(
                uses_model(used, flows, memo, set()) for used in part.uses
            ):
                problems.append(
                    f"操作 {item.name} 的步骤“{part.title}”在写入事务开始后，"
                    "调用了会使用大模型的操作；"
                    "请把它移到第一个保存步骤之前"
                )
    return problems


# 判断一个操作（包括它调用的操作）是否会使用大模型。
def uses_model(
    item: Contract[Any, Any],
    flows: dict[Contract[Any, Any], Flow],
    memo: dict[Contract[Any, Any], bool],
    visiting: set[Contract[Any, Any]],
) -> bool:
    if item in memo:
        return memo[item]
    flow = flows.get(item)
    if flow is None or item in visiting or not isinstance(flow, Flow):
        return False
    visiting.add(item)
    found = any("model" in part.params for part in flow.steps) or any(
        uses_model(used, flows, memo, visiting) for part in flow.steps for used in part.uses
    )
    memo[item] = found
    return found


# 检查不同的错误类没有使用相同的错误码。
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
