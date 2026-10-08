"""
扇出及固定来源的启动检查：公开子操作、Data连线、汇合规则和并发上限。
"""

import math
from typing import TYPE_CHECKING

from shared.pipelines.plan import FanOut, Pipeline, Ratio, Stage

if TYPE_CHECKING:
    from shared.jobs.plan import JobPlan


# 成员用相同的一条公开阶段链，不允许隐藏的嵌套执行器。
def check_group(pipeline: Pipeline, group: FanOut, operations: dict, plans: dict) -> list[str]:
    from shared.pipelines.registration import check_stages

    place = f"流程{pipeline.name}扇出{group.name}"
    problems = []
    if not group.stages or type(group.max_parallel) is not int or group.max_parallel < 1:
        return [f"{place}需要成员阶段和正数max_parallel"]
    if any(isinstance(stage, FanOut) for stage in group.stages):
        return [f"{place}成员阶段不能再嵌套FanOut"]
    if any(stage.freeze_sources for stage in group.stages):
        problems.append(f"{place}成员不能更换固定来源")
    if any(stage.source for stage in group.stages) and not pipeline.stages[0].freeze_sources:
        problems.append(f"{place}读取固定来源，流程首阶段必须freeze_sources=True")
    nested = Pipeline(pipeline.name, group.name, group.stages[0].operation.input, group.stages)
    problems += check_stages(
        nested, operations, plans, source_model=pipeline.stages[0].operation.output
    )
    plan: JobPlan | None = plans.get(group.operation)
    module = operations.get(group.operation)
    flow = module.provides[group.operation] if module else None
    if plan and flow and not any("pipeline" in part.params and part.saves for part in flow.steps):
        problems.append(f"{place}规划操作需要在保存步骤中用pipeline.add_members登记成员")
    if isinstance(group.join, Ratio):
        if not math.isfinite(group.join.success) or not 0 < group.join.success <= 1:
            problems.append(f"{place}Ratio成功比例必须在(0,1]内")
        if len(set(group.join.required)) != len(group.join.required):
            problems.append(f"{place}必需成员键重复")
    return problems


# 只在第一阶段固定来源，读取来源的阶段必须声明相同Data类型。
def check_source(stage: Stage, index: int, source_model: type, place: str) -> list[str]:
    problems = []
    if stage.freeze_sources and index != 0:
        problems.append(f"{place}只有第一阶段可以固定来源")
    if stage.source is not None and stage.source is not source_model:
        problems.append(f"{place}source Data必须和来源阶段产出相同")
    return problems


# 成员产出访问也是Data依赖，只允许读取前面已经声明的扇出阶段。
def check_results(stage: Stage, groups: dict[str, FanOut], place: str) -> list[str]:
    problems = []
    for name, model in stage.members.items():
        group = groups.get(name)
        if group is None or not group.stages or group.stages[-1].operation.output is not model:
            problems.append(f"{place}members中的{name}需要引用前序FanOut及最终产出Data")
    return problems
