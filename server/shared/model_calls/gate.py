"""
步骤收到的 model 参数 ModelGate：只能使用步骤声明过的提示词。
ask() 返回文本；ask_data() 返回按提示词声明的数据类型校验后的结果。
"""

from typing import Any

from shared.data.models import Data
from shared.errors.framework import StepRuleBroken
from shared.model_calls.prompt import Prompt
from shared.model_calls.service import ModelService, parse_output
from shared.records.models import ModelCallRecord


class ModelGate:
    # 绑定大模型服务、步骤允许的提示词和本步骤的调用记录。
    def __init__(
        self,
        service: ModelService | None,
        allowed: tuple[Prompt, ...],
        records: list[ModelCallRecord],
        place: str,
    ) -> None:
        self._service = service
        self._allowed = allowed
        self._records = records
        self._place = place

    # 调用大模型并返回文本。
    async def ask(self, item: Prompt, **values: Any) -> str:
        reply = await self._service_for(item).complete(item, values, self._records)
        return reply.text

    # 调用大模型并把回复校验成声明的数据类型。
    async def ask_data[T: Data](self, item: Prompt, output: type[T], **values: Any) -> T:
        if item.output is not output:
            raise StepRuleBroken(f"提示词「{item.title}」声明的输出类型不是 {output.__name__}")
        reply = await self._service_for(item).complete(item, values, self._records)
        return parse_output(reply.text, output)

    # 检查提示词是否已声明，并返回可用的大模型服务。
    def _service_for(self, item: Prompt) -> ModelService:
        if item not in self._allowed:
            raise StepRuleBroken(f"步骤「{self._place}」使用了未声明的提示词「{item.title}」")
        if self._service is None:
            raise StepRuleBroken("没有配置大模型服务，请检查 APP_MODEL_* 配置")
        return self._service
