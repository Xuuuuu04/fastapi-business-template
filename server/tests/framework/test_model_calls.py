import json
from pathlib import Path

import httpx2
import pytest

from shared.data.fields import meaning
from shared.data.models import Data
from shared.errors.framework import (
    ModelOutputInvalid,
    ModelRejected,
    ModelUnavailable,
    StepRuleBroken,
)
from shared.model_calls.gate import ModelGate
from shared.model_calls.prompt import fill_prompt, load_prompt, prompt
from shared.model_calls.providers import ModelReply, ModelRequest, OpenAICompatible
from shared.model_calls.service import ModelService, parse_output
from shared.records.models import ModelCallRecord
from tests.framework.sample_modules import describe

pytestmark = pytest.mark.anyio


class Verdict(Data):
    passed: bool = meaning("是否通过")


class Flaky:
    name = "flaky"

    def __init__(self, failures: int) -> None:
        self.failures = failures

    async def complete(self, request: ModelRequest) -> ModelReply:
        if self.failures > 0:
            self.failures -= 1
            raise ModelUnavailable("模拟的暂时故障")
        return ModelReply(text="好的", model="flaky", input_tokens=5, output_tokens=2)

    async def close(self) -> None:
        return None


def test_prompt_variables_must_match() -> None:
    text = load_prompt(describe)
    assert text.names == frozenset({"mark"})
    with pytest.raises(StepRuleBroken, match="缺少 \\['mark'\\]"):
        fill_prompt(describe, text, {})
    with pytest.raises(StepRuleBroken, match="多出 \\['extra'\\]"):
        fill_prompt(describe, text, {"mark": "x", "extra": 1})


def test_prompt_needs_user_part(tmp_path: Path) -> None:
    file = tmp_path / "bad.md"
    file.write_text("## system\n只有系统说明", encoding="utf-8")
    with pytest.raises(ValueError, match="缺少“## user”段落"):
        load_prompt(prompt("bad", "坏提示词", file=file, version="1"))


async def test_retry_is_recorded() -> None:
    service = ModelService(Flaky(2), concurrency=1, keep_text=False, retry_waits=(0.0, 0.0))
    records: list[ModelCallRecord] = []
    reply = await service.complete(describe, {"mark": "x"}, records)
    assert reply.text == "好的"
    assert (records[0].retries, records[0].status, records[0].input_tokens) == (2, "ok", 5)


async def test_retry_gives_up() -> None:
    service = ModelService(Flaky(5), concurrency=1, keep_text=False, retry_waits=(0.0,))
    records: list[ModelCallRecord] = []
    with pytest.raises(ModelUnavailable):
        await service.complete(describe, {"mark": "x"}, records)
    assert records[0].status == "failed" and records[0].retries == 1


async def test_gate_checks_declared_prompts() -> None:
    service = ModelService(Flaky(0), concurrency=1, keep_text=False)
    gate = ModelGate(service, (), [], "某个步骤")
    with pytest.raises(StepRuleBroken, match="未声明的提示词"):
        await gate.ask(describe, mark="x")


def test_parse_output() -> None:
    assert parse_output('```json\n{"passed": true}\n```', Verdict).passed is True
    with pytest.raises(ModelOutputInvalid):
        parse_output("通过了", Verdict)


@pytest.mark.parametrize(
    "body",
    ['{"passed":"synthetic-private-reply"}', '{"passed":true,"private":"synthetic-private-reply"}'],
)
def test_parse_output_omits_private_reply(body: str) -> None:
    with pytest.raises(ModelOutputInvalid) as caught:
        parse_output(body, Verdict)
    assert "synthetic-private-reply" not in caught.value.detail
    assert "回复不能转成 Verdict" in caught.value.detail


def fake_server(status: int) -> httpx2.MockTransport:
    def handle(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        assert body["model"] == "demo-model" and body["messages"][-1]["role"] == "user"
        if status != 200:
            return httpx2.Response(status, json={"error": "x"})
        reply = {
            "model": "demo-model",
            "choices": [{"message": {"content": "你好"}, "finish_reason": "stop"}],
        }
        reply["usage"] = {"prompt_tokens": 12, "completion_tokens": 3}
        return httpx2.Response(200, json=reply)

    return httpx2.MockTransport(handle)


async def test_openai_compatible_statuses() -> None:
    request = ModelRequest("p", "系统", "用户", 100, 0.2, False)
    ok = OpenAICompatible("https://model.test/v1", "k", "demo-model", 5, transport=fake_server(200))
    reply = await ok.complete(request)
    assert (reply.text, reply.input_tokens, reply.output_tokens) == ("你好", 12, 3)
    for status, error in ((429, ModelUnavailable), (503, ModelUnavailable), (401, ModelRejected)):
        provider = OpenAICompatible(
            "https://model.test/v1", "k", "demo-model", 5, transport=fake_server(status)
        )
        with pytest.raises(error):
            await provider.complete(request)
        await provider.close()
    await ok.close()
