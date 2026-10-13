"""
步骤观察直接来自实际执行器，字段范围受步骤声明约束，取值不写入普通运行记录。
"""

from typing import Any

from shared.flow.scope import Scope
from shared.flow.step import Step
from shared.scenarios.observations import CURRENT, POSITION, ObservationPoint, ObservationPosition


# 步骤执行成功后才记录观察，跳过或未完成的步骤没有虚构产出。
def record_step(part: Step, values: dict[str, Any], scope: Scope, operation: str) -> None:
    journal = CURRENT.get()
    if journal is None:
        return
    position = scope.observation_position or POSITION.get() or ObservationPosition()
    batch = scope.checkpoint.number + 1 if scope.checkpoint else position.batch
    for name in part.observes:
        point = ObservationPoint(
            operation, part.name, name, batch, position.member, position.attempt
        )
        journal.record(point, values.get(name), observed=name in values, source=part.source)
