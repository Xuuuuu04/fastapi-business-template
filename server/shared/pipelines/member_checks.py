import math
from typing import TYPE_CHECKING

from shared.pipelines.plan import FanOut, Pipeline, Ratio, Stage

if TYPE_CHECKING:
    from shared.jobs.plan import JobPlan


def check_group(pipeline: Pipeline, group: FanOut, operations: dict, plans: dict) -> list[str]:
    from shared.pipelines.registration import check_stages

    place = f"流程 {pipeline.name} 的并行阶段 {group.name}："
    problems = []
    if not group.stages or type(group.max_parallel) is not int or group.max_parallel < 1:
        return [f"{place}必须配置子任务阶段，max_parallel 必须是正整数"]
    if any(isinstance(stage, FanOut) for stage in group.stages):
        return [f"{place}子任务阶段不能再次嵌套 FanOut"]
    if any(stage.freeze_sources for stage in group.stages):
        problems.append(f"{place}子任务不能重新指定固定来源")
    if any(stage.source for stage in group.stages) and not pipeline.stages[0].freeze_sources:
        problems.append(f"{place}需要读取固定来源，流程首阶段必须声明 freeze_sources=True")
    nested = Pipeline(pipeline.name, group.name, group.stages[0].operation.input, group.stages)
    problems += check_stages(
        nested, operations, plans, source_model=pipeline.stages[0].operation.output
    )
    plan: JobPlan | None = plans.get(group.operation)
    module = operations.get(group.operation)
    flow = module.provides[group.operation] if module else None
    if plan and flow and not any("pipeline" in part.params and part.saves for part in flow.steps):
        problems.append(
            f"{place}规划操作必须在 saves=True 的步骤中调用 pipeline.add_members 登记子任务"
        )
    if isinstance(group.join, Ratio):
        if not math.isfinite(group.join.success) or not 0 < group.join.success <= 1:
            problems.append(f"{place}Ratio.success 必须大于 0 且不超过 1")
        if len(set(group.join.required)) != len(group.join.required):
            problems.append(f"{place}Ratio.required 中的必需子任务标识不能重复")
    return problems


def check_source(stage: Stage, index: int, source_model: type, place: str) -> list[str]:
    problems = []
    if stage.freeze_sources and index != 0:
        problems.append(f"{place}只有第一阶段可以保存固定的来源数据")
    if stage.source is not None and stage.source is not source_model:
        problems.append(f"{place}source 的 Data 类型必须与来源阶段的输出类型相同")
    return problems


def check_results(stage: Stage, groups: dict[str, FanOut], place: str) -> list[str]:
    problems = []
    for name, model in stage.members.items():
        group = groups.get(name)
        if group is None or not group.stages or group.stages[-1].operation.output is not model:
            problems.append(
                f"{place}members 中的 {name} 必须引用前面的 FanOut，并使用其最终输出 Data 类型"
            )
    return problems
