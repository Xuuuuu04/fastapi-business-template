"""
大模型入口测试：提示词变量检查、暂时故障重试、结构化结果校验、OpenAI 兼容接口的状态码处理。
不调用真实的大模型服务。
"""

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


# 大模型格式检查测试使用的结构化输出。
class Verdict(Data):
    passed: bool = meaning("是否通过")


# 先失败再成功的模拟大模型服务，用来验证重试行为。
class Flaky:
    name = "flaky"

    # 前几次调用返回暂时故障，之后成功。
    def __init__(self, failures: int) -> None:
        self.failures = failures

    # 模拟一次调用。
    async def complete(self, request: ModelRequest) -> ModelReply:
        if self.failures > 0:
            self.failures -= 1
            raise ModelUnavailable("模拟的暂时故障")
        return ModelReply(text="好的", model="flaky", input_tokens=5, output_tokens=2)

    # 没有需要释放的资源。
    async def close(self) -> None:
        return None


# 提示词变量缺少或多出都会报错。
def test_prompt_variables_must_match() -> None:
    text = load_prompt(describe)
    assert text.names == frozenset({"mark"})
    with pytest.raises(StepRuleBroken, match="缺少 \\['mark'\\]"):
        fill_prompt(describe, text, {})
    with pytest.raises(StepRuleBroken, match="多出 \\['extra'\\]"):
        fill_prompt(describe, text, {"mark": "x", "extra": 1})


# 提示词文件缺少 user 段落时报错。
def test_prompt_needs_user_part(tmp_path: Path) -> None:
    file = tmp_path / "bad.md"
    file.write_text("## system\n只有系统说明", encoding="utf-8")
    with pytest.raises(ValueError, match="缺少“## user”段落"):
        load_prompt(prompt("bad", "坏提示词", file=file, version="1"))


# 暂时故障按次数重试，重试次数写进调用记录。
async def test_retry_is_recorded() -> None:
    service = ModelService(Flaky(2), concurrency=1, keep_text=False, retry_waits=(0.0, 0.0))
    records: list[ModelCallRecord] = []
    reply = await service.complete(describe, {"mark": "x"}, records)
    assert reply.text == "好的"
    assert (records[0].retries, records[0].status, records[0].input_tokens) == (2, "ok", 5)


# 重试次数用完仍失败时，记录失败并抛出暂时故障。
async def test_retry_gives_up() -> None:
    service = ModelService(Flaky(5), concurrency=1, keep_text=False, retry_waits=(0.0,))
    records: list[ModelCallRecord] = []
    with pytest.raises(ModelUnavailable):
        await service.complete(describe, {"mark": "x"}, records)
    assert records[0].status == "failed" and records[0].retries == 1


# 步骤只能使用声明过的提示词。
async def test_gate_checks_declared_prompts() -> None:
    service = ModelService(Flaky(0), concurrency=1, keep_text=False)
    gate = ModelGate(service, (), [], "某个步骤")
    with pytest.raises(StepRuleBroken, match="未声明的提示词"):
        await gate.ask(describe, mark="x")


# 结构化结果：代码块中的 JSON 可以解析，格式不对时报可以重试的错误。
def test_parse_output() -> None:
    assert parse_output('```json\n{"passed": true}\n```', Verdict).passed is True
    with pytest.raises(ModelOutputInvalid):
        parse_output("通过了", Verdict)


# 校验器自己的说明可能含输入值和自定义规则，统一失败说明不带模型原文。
@pytest.mark.parametrize(
    "body",
    ['{"passed":"synthetic-private-reply"}', '{"passed":true,"private":"synthetic-private-reply"}'],
)
def test_parse_output_omits_private_reply(body: str) -> None:
    with pytest.raises(ModelOutputInvalid) as caught:
        parse_output(body, Verdict)
    assert "synthetic-private-reply" not in caught.value.detail
    assert "回复不能转成 Verdict" in caught.value.detail


# 按状态码返回不同结果的模拟服务。
def fake_server(status: int) -> httpx2.MockTransport:
    # 返回固定状态码；200 时带上回复和用量。
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


# OpenAI 兼容接口：200 取出文本和用量，429 和 5xx 是暂时故障，其他 4xx 是配置问题。
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
