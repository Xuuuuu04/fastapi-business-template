import hashlib
import json
from typing import TYPE_CHECKING, Any

from shared.data.models import Data
from shared.errors.framework import InvalidInput
from shared.pipelines.plan import FanOut, Pipeline, Stage, Wait

if TYPE_CHECKING:
    from shared.modules.catalog import Catalog

MAX_DATA_BYTES = 16 * 1024


def format_of(model: type[Data] | None) -> Any:
    return None if model is None else structural(model.model_json_schema())


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


def declarations(pipeline: Pipeline, catalog: "Catalog") -> list[dict[str, str]]:
    return [stage_declaration(stage, catalog) for stage in pipeline.stages]


def stage_declaration(stage: Stage, catalog: "Catalog") -> dict[str, str]:
    plan = catalog.plan(stage.operation.name)
    shape = dict(
        contract=stage.operation.name,
        input=format_of(stage.operation.input),
        output=format_of(stage.operation.output),
        input_from=stage.input_from,
        cursor=format_of(plan.cursor if plan else None),
        segmented=bool(plan and plan.segmented),
        source=[stage.freeze_sources, format_of(stage.source)],
        member_results={name: format_of(model) for name, model in stage.members.items()},
    )
    if isinstance(stage, Wait):
        shape["wait"] = [stage.ready_field, stage.every, stage.timeout, stage.max_parallel]
    if isinstance(stage, FanOut):
        shape["members"] = [stage_declaration(child, catalog) for child in stage.stages]
        shape["group"] = group_signature(stage)
    raw = json.dumps(shape, sort_keys=True, ensure_ascii=False)
    result = dict(
        name=stage.name,
        contract=stage.operation.name,
        signature=hashlib.sha256(raw.encode()).hexdigest(),
    )
    if isinstance(stage, FanOut):
        result["group"] = group_signature(stage)
    return result


def group_signature(group: FanOut) -> str:
    shape = [
        type(group.join).__name__,
        getattr(group.join, "success", 1),
        getattr(group.join, "required", ()),
        group.max_parallel,
    ]
    return hashlib.sha256(json.dumps(shape).encode()).hexdigest()


def data_json(model: type[Data], value: Data, stage: str) -> str:
    if not isinstance(value, model):
        raise InvalidInput(f"流程阶段{stage}的数据必须是声明过的{model.__name__}")
    body = value.model_dump_json()
    if len(body.encode("utf-8")) > MAX_DATA_BYTES:
        raise InvalidInput(f"流程阶段{stage}的数据超过16 KiB，请只传版本号或引用")
    return body


def input_source(pipeline: Pipeline, index: int) -> str:
    stage: Stage = pipeline.stages[index]
    if stage.input_from == "previous":
        return "input" if index == 0 else pipeline.stages[index - 1].name
    return stage.input_from
