"""
外部效果声明与适配协议；受理、完成和模拟结果分别表达，不用一次函数返回推定业务完成。
"""

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


# 产品声明供应商能力，凭据与连接由组装工厂提供，不进入声明摘要。
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

    # 声明和协议变化使旧意图无法悄悄切换适配器语义。
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

    # 相同业务键只复用同一协议的意图，不把新协议当旧请求恢复。
    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.shape(), sort_keys=True).encode()).hexdigest()

    # 适配器启动前检查预算、类型和业务字段声明。
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


# 适配器的回执由供应商语义决定，数据必须通过ProviderSpec.output校验。
@dataclass(frozen=True)
class AdapterReply:
    state: EffectState
    data: Data | None = None
    external_id: str = ""


# SDK、SMTP与HTTP适配器实现同一协议，模拟属性不能被产品调用方覆盖。
class EffectAdapter(Protocol):
    simulated: bool
    identity: str

    # 发送一次；稳定编号由框架生成，重复安全性必须来自供应商保证。
    async def send(self, input: Data, key: str) -> AdapterReply: ...

    # 查询旧请求；只有权威的未执行结果才可以返回not_sent。
    async def lookup(self, input: Data, key: str) -> AdapterReply: ...

    # 释放产品客户端，不在退出时重发或修改未知意图。
    async def close(self) -> None: ...


# 公开结果保留持久意图编号，允许分别观察模拟、上游受理和真实完成。
class EffectResult[Out: Data](Data):
    id: str = meaning("持久外部意图编号")
    state: EffectState = meaning("未发送、拒绝、受理、完成或未知")
    data: Out | None = meaning("供应商校验后的回执", default=None, empty="尚未取得回执")
    external_id: str = meaning("供应商编号", default="", empty="供应商未提供")
    simulated: bool = meaning("是否由模拟适配器产生")
