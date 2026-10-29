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
    transport: Literal["http", "smtp", "sdk"]
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
            problems.append("ProviderSpec名称应为供应商.动作")
        if not self.title.strip() or self.transport not in {"http", "smtp", "sdk"}:
            problems.append(f"外部效果 {self.name} 的用途或传输类型无效")
        if not math.isfinite(self.timeout) or self.timeout <= 0 or self.concurrency < 1:
            problems.append(f"外部效果 {self.name} 的预算必须为正数")
        for model in (self.input, self.output):
            if not isinstance(model, type) or not issubclass(model, Data):
                problems.append(f"外部效果 {self.name} 的输入输出必须为Data")
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
    id: str = meaning("持久外部意图编号")
    state: EffectState = meaning("未发送、拒绝、受理、完成或未知")
    data: Out | None = meaning("供应商校验后的回执", default=None, empty="尚未取得回执")
    external_id: str = meaning("供应商编号", default="", empty="供应商未提供")
    simulated: bool = meaning("是否由模拟适配器产生")
