"""
大模型调用服务：限制并发、统一重试、记录每次调用的模型、提示词版本、用量和耗时。
步骤不直接使用本服务，而是通过执行器注入的 model 参数（ModelGate）调用。
"""

import asyncio
import json
import time
from typing import Any

from pydantic import ValidationError

from shared.data.models import Data
from shared.errors.framework import ModelOutputInvalid, ModelUnavailable
from shared.errors.kinds import BusinessError
from shared.model_calls.prompt import Prompt, PromptText, fill_prompt, load_prompt
from shared.model_calls.providers import ModelProvider, ModelReply, ModelRequest
from shared.records.models import ModelCallRecord
from shared.remote_calls.breaker import Breaker

RETRY_WAITS = (1.0, 3.0)
KEPT_TEXT = 2000


# 执行已登记的提示词，检查输出格式并管理并发与失败重试。
class ModelService:
    # 设置服务商实现、并发上限、是否保存截断后的原文，以及暂时故障后的重试等待秒数。
    def __init__(
        self,
        provider: ModelProvider,
        *,
        concurrency: int,
        keep_text: bool,
        retry_waits: tuple[float, ...] = RETRY_WAITS,
    ) -> None:
        self.provider = provider
        self.limit = asyncio.Semaphore(concurrency)
        self.keep_text = keep_text
        self.retry_waits = retry_waits
        self.texts: dict[Prompt, PromptText] = {}
        self.breaker = Breaker()

    # 启动时读取并检查全部提示词文件。
    def load(self, prompts: list[Prompt]) -> None:
        for item in prompts:
            self.texts[item] = load_prompt(item)

    # 调用一次大模型：填充提示词、限流、重试，并把调用情况写进 records。
    async def complete(
        self, item: Prompt, values: dict[str, object], records: list[ModelCallRecord]
    ) -> ModelReply:
        text = self.texts.get(item) or load_prompt(item)
        system, user = fill_prompt(item, text, values)
        request = ModelRequest(
            item.name, system, user, item.max_tokens, item.temperature, item.output is not None
        )
        record = ModelCallRecord(item.name, item.version, "", "running", 0.0)
        records.append(record)
        started = time.perf_counter()
        try:
            reply = await self.send(request, record)
        except BaseException as error:
            record.status = "failed"
            record.error = getattr(error, "detail", type(error).__name__)
            raise
        finally:
            record.elapsed_ms = (time.perf_counter() - started) * 1000
        record.status, record.model = "ok", reply.model
        record.input_tokens, record.output_tokens = reply.input_tokens, reply.output_tokens
        if self.keep_text:
            record.prompt_text, record.reply_text = user[:KEPT_TEXT], reply.text[:KEPT_TEXT]
        return reply

    # 在并发上限内发送请求；连续失败时连续失败后暂停调用，暂停期间直接失败。
    async def send(self, request: ModelRequest, record: ModelCallRecord) -> ModelReply:
        wait = self.breaker.blocked()
        if wait:
            raise ModelUnavailable(f"大模型服务连续失败，暂停调用，{wait:.0f} 秒后再试")
        try:
            reply = await self.attempts(request, record)
        except ModelUnavailable:
            self.breaker.failed()
            raise
        except BusinessError:
            self.breaker.succeeded()
            raise
        except BaseException:
            self.breaker.released()
            raise
        self.breaker.succeeded()
        return reply

    # 暂时故障按 retry_waits 的次数和间隔重试。
    async def attempts(self, request: ModelRequest, record: ModelCallRecord) -> ModelReply:
        for attempt in range(len(self.retry_waits) + 1):
            try:
                async with self.limit:
                    return await self.provider.complete(request)
            except ModelUnavailable:
                if attempt == len(self.retry_waits):
                    raise
                record.retries += 1
                await asyncio.sleep(self.retry_waits[attempt])
        raise ModelUnavailable("大模型调用重试次数已用完")

    # 关闭服务商连接。
    async def close(self) -> None:
        await self.provider.close()


# 从回复文本中取出 JSON，并按声明的数据类型校验。
def parse_output[T: Data](text: str, output: type[T]) -> T:
    body = text.strip()
    if body.startswith("```"):
        body = body.strip("`").split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        raw: Any = json.loads(body)
        return output.model_validate(raw)
    except (json.JSONDecodeError, ValidationError):
        raise ModelOutputInvalid(
            f"回复不能转成 {output.__name__}，请检查回复格式与字段要求"
        ) from None
