"""
把module.py里的Pipeline登记为普通公开启动操作；阶段只引用已有公开任务。
"""

import math
import re
from collections.abc import Sequence
from dataclasses import replace
from typing import Any, cast

from shared.data.models import Data
from shared.flow.flow import Flow
from shared.flow.step import step
from shared.jobs.plan import JobPlan
from shared.modules.module import Module
from shared.pipelines.gate import PipelineGate
from shared.pipelines.member_checks import check_group, check_results, check_source
from shared.pipelines.plan import FanOut, Pipeline, StartWork, Wait
from shared.pipelines.schema import input_source

NAME = re.compile(r"^[a-z][a-z0-9_]*$")


# 生成入口在普通执行器内开启事务，复用相同的登记和运行图。
@step("登记流程与第一阶段", reads=["request"], writes=["result"], saves=True)
async def start_pipeline(data: StartWork, pipeline: PipelineGate) -> None:
    data.result = await pipeline.start(data.request)


# 保留业务存储和操作，把启动能力加入本模块登记。
def expand(modules: Sequence[Module]) -> list[Module]:
    result = []
    for module in modules:
        provides, plans = dict(module.provides), list(module.jobs)
        for pipeline in module.pipelines:
            provides[pipeline.start] = Flow(
                pipeline.title,
                work=cast(Any, StartWork)[pipeline.input],
                result="result",
                steps=[start_pipeline],
            )
            plans.append(JobPlan(pipeline.start, repeat_safe=True))
        result.append(replace(module, provides=provides, jobs=tuple(plans)))
    return result


# 流程类型、输入来源和等待操作在启动前核对，不运行任何业务代码。
def check_pipelines(modules: Sequence[Module]) -> list[str]:
    operations = {op: module for module in modules for op in module.provides}
    plans = {plan.contract: plan for module in modules for plan in module.jobs}
    problems, seen = [], set()
    for module in modules:
        for pipeline in module.pipelines:
            if (
                not re.fullmatch(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*", pipeline.name)
                or pipeline.name in seen
                or pipeline.name.split(".")[0] != module.name
            ):
                problems.append(f"流程{pipeline.name}名称重复或不属于{module.name}")
            seen.add(pipeline.name)
            if pipeline.overlap not in ("skip", "queue") or not pipeline.stages:
                problems.append(f"流程{pipeline.name}需要阶段和有效overlap")
            if (
                any(stage.source is not None for stage in pipeline.stages)
                and not pipeline.stages[0].freeze_sources
            ):
                problems.append(f"流程{pipeline.name}使用固定来源，首阶段必须freeze_sources=True")
            problems += check_stages(pipeline, operations, plans)
    return problems


# 输入按声明过的Data传递，分段阶段必须明确游标Data格式。
def check_stages(
    pipeline: Pipeline, operations: dict, plans: dict, *, source_model: type | None = None
) -> list[str]:
    problems, outputs = [], {"input": pipeline.input}
    if not isinstance(pipeline.input, type) or not issubclass(pipeline.input, Data):
        return [f"流程{pipeline.name}初始输入必须是Data"]
    groups: dict[str, FanOut] = {}
    for index, stage in enumerate(pipeline.stages):
        place = f"流程{pipeline.name}阶段{stage.name}"
        if not NAME.fullmatch(stage.name) or stage.name in outputs:
            problems.append(f"{place}名称无效或重复")
        source = input_source(pipeline, index)
        if (
            stage.operation not in operations
            or stage.operation not in plans
            or not stage.operation.entry
        ):
            problems.append(f"{place}必须引用已登记的公开后台操作")
        if outputs.get(source) is not stage.operation.input:
            problems.append(f"{place}输入Data与来源{source}不一致")
        outputs[stage.name] = stage.operation.output
        plan = plans.get(stage.operation)
        if plan and plan.segmented and plan.cursor is None:
            problems.append(f"{place}分段任务必须声明cursor Data")
        problems += check_source(
            stage, index, source_model or pipeline.stages[0].operation.output, place
        )
        problems += check_results(stage, groups, place)
        if isinstance(stage, FanOut):
            groups[stage.name] = stage
            problems += check_group(pipeline, stage, operations, plans)
        if isinstance(stage, Wait):
            problems += check_wait(stage, plan, place)
    return problems


# 等待检查必须有明确条件、时间限制，且可以安全重复。
def check_wait(stage: Wait, plan: JobPlan | None, place: str) -> list[str]:
    problems = []
    field = stage.operation.output.model_fields.get(stage.ready_field)
    if not field or field.annotation is not bool:
        problems.append(f"{place}等待条件必须是产出中的bool字段")
    if (
        not math.isfinite(stage.every)
        or not math.isfinite(stage.timeout)
        or min(stage.every, stage.timeout) <= 0
        or type(stage.max_parallel) is not int
        or stage.max_parallel < 1
    ):
        problems.append(f"{place}等待间隔、上限和max_parallel必须为正数")
    if plan and (not plan.repeat_safe or plan.segmented):
        problems.append(f"{place}等待检查必须可安全重复，不能是分段任务")
    return problems
