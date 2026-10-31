import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from shared.data.fields import check_notes, meaning
from shared.data.models import Data
from shared.errors.framework import DeclarationError

EffectState = Literal["not_sent", "refused", "accepted", "completed", "unknown"]


@dataclass(frozen=True, eq=False)
class ProviderSpec[In: Data, Out: Data]:
    name: str
    title: str
    input: type[In]
    output: type[Out]
    transport: Literal["smtp", "sdk"]
    repeat_safe: bool = False
    timeout: float = 10.0
    concurrency: int = 8

    def shape(self) -> dict[str, Any]:
        return dict(
            name=self.name,
            title=self.title,
            transport=self.transport,
            input=self.input.model_json_schema(),
            output=self.output.model_json_schema(),
            repeat_safe=self.repeat_safe,
            timeout=self.timeout,
            concurrency=self.concurrency,
        )

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.shape(), sort_keys=True).encode()).hexdigest()

    def validate(self) -> None:
        problems = []
        if not re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+", self.name):
            problems.append("ProviderSpec 的名称应写成“服务名.动作名”")
        if not self.title.strip() or self.transport not in {"smtp", "sdk"}:
            problems.append(f"外部调用 {self.name} 的用途不能为空，传输类型只能是 smtp 或 sdk")
        if not math.isfinite(self.timeout) or self.timeout <= 0 or self.concurrency < 1:
            problems.append(f"外部调用 {self.name} 的超时秒数必须为有限正数，并发数至少为 1")
        for model in (self.input, self.output):
            if not isinstance(model, type) or not issubclass(model, Data):
                problems.append(f"外部调用 {self.name} 的输入和输出必须是 Data 的子类")
            else:
                problems += check_notes(model, self.name)
        if problems:
            raise DeclarationError(problems)


@dataclass(frozen=True)
class AdapterReply:
    state: EffectState
    data: Data | None = None
    external_id: str = ""


class EffectAdapter(Protocol):
    simulated: bool
    identity: str

    async def send(self, input: Data, key: str) -> AdapterReply: ...

    async def lookup(self, input: Data, key: str) -> AdapterReply: ...

    async def close(self) -> None: ...


class EffectResult[Out: Data](Data):
    id: str = meaning("已保存的外部请求记录编号，用于查询原请求")
    state: EffectState = meaning(
        "外部请求状态：not_sent 未发送、refused 已拒绝、accepted 已受理、"
        "completed 已完成、unknown 待确认"
    )
    data: Out | None = meaning(
        "外部服务返回且已通过格式校验的结果", default=None, empty="尚未取得外部服务的返回结果"
    )
    external_id: str = meaning("外部服务返回的请求编号", default="", empty="外部服务未提供请求编号")
    simulated: bool = meaning("是否使用模拟结果，未调用真实外部服务")
