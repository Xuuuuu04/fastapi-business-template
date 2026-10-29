import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, get_args

from shared.access.caller import Caller
from shared.data.fields import meaning
from shared.data.models import Data
from shared.errors.framework import StepRuleBroken

if TYPE_CHECKING:
    from shared.jobs.plan import JobPlan


@dataclass(frozen=True)
class SerialKey:
    namespace: str
    field: str


@dataclass(frozen=True)
class ResourceLimit:
    name: str
    concurrency: int = 1
    cooldown: float = 0


class Validity(Data):
    valid: bool = meaning("关键业务状态是否仍允许执行")
    reason: str = meaning("不能执行的具体原因", default="", empty="仍有效")


def input_field(input: Data, path: str) -> Any:
    value: Any = input
    for part in path.split("."):
        if not isinstance(value, Data) or part not in type(value).model_fields:
            raise StepRuleBroken(f"任务输入字段 {path} 不存在")
        value = getattr(value, part)
    return value


def submission_limits(plan: "JobPlan", input: Data, caller: Caller, now: float) -> dict[str, Any]:
    serial_key = ""
    if plan.serial is not None:
        value = input_field(input, plan.serial.field)
        if type(value) not in {str, int} or not str(value) or len(str(value)) > 512:
            raise StepRuleBroken("串行业务键必须为有界字符串或整数")
        body = json.dumps([plan.serial.namespace, caller.org_id, value])
        serial_key = hashlib.sha256(body.encode()).hexdigest()
    valid_until = None
    if plan.valid_until_field:
        value = input_field(input, plan.valid_until_field)
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise StepRuleBroken("任务有效期必须是带时区的datetime")
        valid_until = value.timestamp()
    return dict(
        serial_key=serial_key or None,
        valid_until=valid_until,
        queued_until=now + plan.queue_timeout if plan.queue_timeout else None,
    )


def limit_problems(plan: "JobPlan") -> list[str]:
    problems = resource_problems(plan.resources, plan.contract.name)
    if plan.attempt_timeout is not None and (
        not math.isfinite(plan.attempt_timeout) or plan.attempt_timeout <= 0
    ):
        problems.append(f"任务 {plan.contract.name} 的单次尝试预算无效")
    if plan.queue_timeout is not None and (
        not math.isfinite(plan.queue_timeout) or plan.queue_timeout <= 0
    ):
        problems.append(f"任务 {plan.contract.name} 的排队预算无效")
    paths = [plan.valid_until_field, plan.serial.field if plan.serial else ""]
    for path in filter(None, paths):
        if declared_field(plan.contract.input, path) is None:
            problems.append(f"任务 {plan.contract.name} 的输入字段 {path} 未声明")
    if plan.serial and not re.fullmatch(r"[a-z][a-z0-9_.-]{0,99}", plan.serial.namespace):
        problems.append(f"任务 {plan.contract.name} 的串行名称无效")
    if plan.revalidate is not None and (
        plan.revalidate.effect != "query"
        or plan.revalidate.input is not plan.contract.input
        or not issubclass(plan.revalidate.output, Validity)
    ):
        problems.append(f"任务 {plan.contract.name} 的revalidate必须是同输入、Validity输出的查询")
    return problems


def resource_problems(resources: tuple[ResourceLimit, ...], operation: str) -> list[str]:
    problems = []
    names = [resource.name for resource in resources]
    if len(names) != len(set(names)):
        problems.append(f"任务 {operation} 的资源重复")
    for resource in resources:
        if not re.fullmatch(r"[a-z][a-z0-9_.-]{0,99}", resource.name):
            problems.append(f"资源 {resource.name} 的名称无效")
        if type(resource.concurrency) is not int or resource.concurrency < 1:
            problems.append(f"资源 {resource.name} 的并发必须是正整数")
        if not math.isfinite(resource.cooldown) or resource.cooldown < 0:
            problems.append(f"资源 {resource.name} 的冷却无效")
    return problems


def declared_field(model: type[Data], path: str) -> Any:
    current: Any = model
    for part in path.split("."):
        if not isinstance(current, type) or not issubclass(current, Data):
            choices = [
                value
                for value in get_args(current)
                if isinstance(value, type) and issubclass(value, Data)
            ]
            if len(choices) != 1:
                return None
            current = choices[0]
        field = current.model_fields.get(part)
        if field is None:
            return None
        current = field.annotation
    return current
