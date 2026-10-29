from datetime import datetime
from typing import get_args

from shared.data.models import Data
from shared.jobs.plan import Schedule


def check_slot(schedule: Schedule) -> list[str]:
    if not schedule.slot_input_field:
        return []
    parts = schedule.slot_input_field.split(".")
    value: object = schedule.input
    for index, part in enumerate(parts):
        if not isinstance(value, Data) or part not in type(value).model_fields:
            return [f"定时计划{schedule.name}的周期字段{schedule.slot_input_field}不存在"]
        annotation = type(value).model_fields[part].annotation
        if index == len(parts) - 1:
            if annotation is not datetime and datetime not in get_args(annotation):
                return [f"定时计划{schedule.name}的周期字段必须是datetime"]
        else:
            value = getattr(value, part)
    return []
