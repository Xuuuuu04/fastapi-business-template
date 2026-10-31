from collections.abc import Callable
from typing import Any

from shared.data.models import Data
from shared.errors.framework import StepRuleBroken
from shared.model_calls.prompt import Prompt
from shared.model_calls.service import ModelService, parse_output
from shared.records.models import ModelCallRecord


class ModelGate:
    def __init__(
        self,
        service: ModelService | None,
        allowed: tuple[Prompt, ...],
        records: list[ModelCallRecord],
        place: str,
        transaction_started: Callable[[], bool] | None = None,
    ) -> None:
        self._service = service
        self._allowed = allowed
        self._records = records
        self._place = place
        self._transaction_started = transaction_started

    async def ask(self, item: Prompt, **values: Any) -> str:
        reply = await self._service_for(item).complete(item, values, self._records)
        return reply.text

    async def ask_data[T: Data](self, item: Prompt, output: type[T], **values: Any) -> T:
        if item.output is not output:
            raise StepRuleBroken(f"提示词“{item.title}”声明的输出类型不是 {output.__name__}")
        reply = await self._service_for(item).complete(item, values, self._records)
        return parse_output(reply.text, output)

    def _service_for(self, item: Prompt) -> ModelService:
        if self._transaction_started is not None and self._transaction_started():
            raise StepRuleBroken(f"步骤“{self._place}”在写入事务开始后不能调用大模型")
        if item not in self._allowed:
            raise StepRuleBroken(f"步骤“{self._place}”使用了未声明的提示词“{item.title}”")
        if self._service is None:
            raise StepRuleBroken("没有配置大模型服务，请检查 APP_MODEL_* 配置")
        return self._service
