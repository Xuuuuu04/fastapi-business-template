"""
流程传递的Data和后续阶段兼容性：只比较格式与声明，不把内部实现或模块版本当作暂停条件。
"""

import hashlib
import json
from typing import TYPE_CHECKING, Any

from shared.data.models import Data
from shared.errors.framework import InvalidInput
from shared.pipelines.plan import Pipeline, Stage, Wait

if TYPE_CHECKING:
    from shared.modules.catalog import Catalog

MAX_DATA_BYTES = 16 * 1024


# 格式摘要忽略说明与标题，保留字段类型、约束、必填和默认值。
def format_of(model: type[Data] | None) -> Any:
    return None if model is None else structural(model.model_json_schema())


# 文档文字变化不触发版本暂停，业务格式变化保留在摘要中。
def structural(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: structural(item)
            for key, item in value.items()
            if key not in ("title", "description", "examples")
        }
    if isinstance(value, list):
        return [structural(item) for item in value]
    return value


# 每个阶段的输入输出、游标和阶段声明共同决定恢复兼容性。
def declarations(pipeline: Pipeline, catalog: "Catalog") -> list[dict[str, str]]:
    result = []
    for stage in pipeline.stages:
        plan = catalog.plan(stage.operation.name)
        shape = dict(
            contract=stage.operation.name,
            input=format_of(stage.operation.input),
            output=format_of(stage.operation.output),
            input_from=stage.input_from,
            cursor=format_of(plan.cursor if plan else None),
            segmented=bool(plan and plan.segmented),
        )
        if isinstance(stage, Wait):
            shape["wait"] = [stage.ready_field, stage.every, stage.timeout, stage.max_parallel]
        raw = json.dumps(shape, sort_keys=True, ensure_ascii=False)
        result.append(
            {
                "name": stage.name,
                "contract": stage.operation.name,
                "signature": hashlib.sha256(raw.encode()).hexdigest(),
            }
        )
    return result


# Data必须符合声明且有界，错误明确指出输入或产出所属阶段。
def data_json(model: type[Data], value: Data, stage: str) -> str:
    if not isinstance(value, model):
        raise InvalidInput(f"流程阶段{stage}的数据必须是声明过的{model.__name__}")
    body = value.model_dump_json()
    if len(body.encode("utf-8")) > MAX_DATA_BYTES:
        raise InvalidInput(f"流程阶段{stage}的数据超过16 KiB，请只传版本号或引用")
    return body


# 取得阶段的明确输入来源，previous只指声明中的前一个阶段。
def input_source(pipeline: Pipeline, index: int) -> str:
    stage: Stage = pipeline.stages[index]
    if stage.input_from == "previous":
        return "input" if index == 0 else pipeline.stages[index - 1].name
    return stage.input_from
