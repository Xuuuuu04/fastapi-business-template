"""
分段任务的启动检查：明确声明重试安全性，操作必须使用恢复游标。
普通任务误用 checkpoint 时在启动阶段指出声明位置。
"""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from shared.data.models import Data
from shared.flow.flow import Flow
from shared.jobs.imports import check_import
from shared.jobs.limits import limit_problems
from shared.jobs.organizations import validate_orgs
from shared.jobs.slot import check_slot
from shared.modules.module import Module


# 分段任务必须能安全重试本批，并直接声明它的恢复位置。
def check_segmented_jobs(module: Module) -> list[str]:
    problems = []
    for plan in module.jobs:
        problems += limit_problems(plan)
        if plan.import_plan is not None:
            problems += check_import(plan.import_plan, module.tables)
            if not plan.segmented:
                problems.append(f"导入任务 {plan.contract.name} 必须声明 segmented=True")
        if plan.cursor is not None and (
            not isinstance(plan.cursor, type) or not issubclass(plan.cursor, Data)
        ):
            problems.append(f"任务 {plan.contract.name} 的cursor必须是Data类型")
        flow = module.provides.get(plan.contract)
        has_checkpoint = isinstance(flow, Flow) and any(
            "checkpoint" in part.params for part in flow.steps
        )
        if not plan.segmented:
            if has_checkpoint:
                problems.append(
                    f"任务 {plan.contract.name} 使用 checkpoint，需要声明 segmented=True"
                )
            continue
        if not plan.repeat_safe:
            problems.append(f"分段任务 {plan.contract.name} 必须声明 repeat_safe=True")
        if isinstance(flow, Flow) and not has_checkpoint:
            problems.append(f"分段任务 {plan.contract.name} 必须使用 checkpoint 声明恢复位置")
    return problems


# 组织和周期输入在启动时检查，不等待定时执行才发现声明错误。
def check_schedules(module: Module) -> list[str]:
    problems = []
    for schedule in module.schedules:
        if schedule.org_ids is not None:
            try:
                validate_orgs(schedule.org_ids)
            except ValueError as error:
                problems.append(f"定时计划{schedule.name}：{error}")
        problems += check_slot(schedule)
    return problems


# 检查后台任务和定时计划的声明。
def check_jobs(module: Module) -> list[str]:
    problems = []
    problems += check_segmented_jobs(module)
    problems += check_schedules(module)
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
