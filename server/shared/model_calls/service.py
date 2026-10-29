import asyncio
import json
from typing import Any

from pydantic import ValidationError

from shared.data.models import Data
from shared.errors.framework import ModelOutputInvalid, ModelUnavailable
from shared.errors.kinds import BusinessError
from shared.model_calls.prompt import Prompt, PromptText, fill_prompt, load_prompt
from shared.model_calls.providers import ModelProvider, ModelReply, ModelRequest
from shared.records.models import ModelCallRecord
from shared.remote_calls.breaker import Breaker
from shared.timing.clock import Clock, RealClock
from shared.timing.current import clocked, monotonic, sleep

RETRY_WAITS = (1.0, 3.0)
KEPT_TEXT = 2000


class ModelService:
    def __init__(
        self,
        provider: ModelProvider,
        *,
        concurrency: int,
        keep_text: bool,
        retry_waits: tuple[float, ...] = RETRY_WAITS,
    ) -> None:
        self.clock: Clock = RealClock()

        self.provider = provider
        self.limit = asyncio.Semaphore(concurrency)
        self.keep_text = keep_text
        self.retry_waits = retry_waits
        self.texts: dict[Prompt, PromptText] = {}
        self.breaker = Breaker(clock=lambda: self.clock.monotonic())

    def load(self, prompts: list[Prompt]) -> None:
        for item in prompts:
            self.texts[item] = load_prompt(item)

    @clocked
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
        started = monotonic()
        try:
            reply = await self.send(request, record)
        except BaseException as error:
            record.status = "failed"
            record.error = getattr(error, "detail", type(error).__name__)
            raise
        finally:
            record.elapsed_ms = (monotonic() - started) * 1000
        record.status, record.model = "ok", reply.model
        record.input_tokens, record.output_tokens = reply.input_tokens, reply.output_tokens
        if self.keep_text:
            record.prompt_text, record.reply_text = user[:KEPT_TEXT], reply.text[:KEPT_TEXT]
        return reply

    @clocked
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

    @clocked
    async def attempts(self, request: ModelRequest, record: ModelCallRecord) -> ModelReply:
        for attempt in range(len(self.retry_waits) + 1):
            try:
                async with self.limit:
                    return await self.provider.complete(request)
            except ModelUnavailable:
                if attempt == len(self.retry_waits):
                    raise
                record.retries += 1
                await sleep(self.retry_waits[attempt])
        raise ModelUnavailable("大模型调用重试次数已用完")

    @clocked
    async def close(self) -> None:
        await self.provider.close()


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
