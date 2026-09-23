"""
大模型服务的统一约定 ModelProvider，以及两个实现：
OpenAICompatible 调用 OpenAI 兼容的 /chat/completions 接口，覆盖多数国内外服务商；
FakeModel 返回固定文本，用于测试和没有配置模型的本地开发，不产生费用。
要接入 Claude，请另写一个基于官方 anthropic SDK 的实现，不要通过兼容接口转接。
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import httpx2

from shared.errors.framework import ModelRejected, ModelUnavailable


@dataclass(frozen=True)
class ModelRequest:
    prompt: str
    system: str
    user: str
    max_tokens: int
    temperature: float
    wants_json: bool


@dataclass(frozen=True)
class ModelReply:
    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish: str = ""


class ModelProvider(Protocol):
    name: str

    # 发送一次请求并返回回复；暂时故障抛 ModelUnavailable，请求被拒绝抛 ModelRejected。
    async def complete(self, request: ModelRequest) -> ModelReply: ...

    # 释放网络连接。
    async def close(self) -> None: ...


class OpenAICompatible:
    name = "openai_compatible"

    # 设置服务地址、密钥、模型名和超时时间；transport 只在测试中替换。
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self.client = httpx2.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )

    # 调用 /chat/completions，并把网络和状态码错误转成框架的错误种类。
    async def complete(self, request: ModelRequest) -> ModelReply:
        try:
            response = await self.client.post("/chat/completions", json=self.body(request))
        except httpx2.TimeoutException as error:
            raise ModelUnavailable("大模型服务响应超时") from error
        except httpx2.TransportError as error:
            raise ModelUnavailable("无法连接大模型服务") from error
        if response.status_code == 429 or response.status_code >= 500:
            raise ModelUnavailable(f"大模型服务暂时不可用（HTTP {response.status_code}）")
        if response.status_code >= 400:
            raise ModelRejected(f"大模型服务拒绝请求（HTTP {response.status_code}）")
        return self.reply(response.json())

    # 组装请求正文。
    def body(self, request: ModelRequest) -> dict[str, Any]:
        messages = [{"role": "user", "content": request.user}]
        if request.system:
            messages.insert(0, {"role": "system", "content": request.system})
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.wants_json:
            body["response_format"] = {"type": "json_object"}
        return body

    # 从响应正文取出文本和用量。
    def reply(self, data: dict[str, Any]) -> ModelReply:
        try:
            choice = data["choices"][0]
            text = choice["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as error:
            raise ModelUnavailable("大模型服务返回的格式无法识别") from error
        usage = data.get("usage") or {}
        return ModelReply(
            text=text,
            model=str(data.get("model", self.model)),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            finish=str(choice.get("finish_reason", "")),
        )

    # 关闭连接池。
    async def close(self) -> None:
        await self.client.aclose()


Answer = str | Callable[[ModelRequest], str]


class FakeModel:
    name = "fake"

    # replies 按提示词名称给出固定回复或生成回复的函数；未指定的提示词返回默认文本。
    def __init__(self, replies: Mapping[str, Answer] | None = None) -> None:
        self.replies = dict(replies or {})
        self.requests: list[ModelRequest] = []

    # 返回预设的回复，并记下收到的请求，方便测试检查。
    async def complete(self, request: ModelRequest) -> ModelReply:
        self.requests.append(request)
        answer = self.replies.get(request.prompt, "（本地模拟回复，没有调用真实模型）")
        text = answer(request) if callable(answer) else answer
        return ModelReply(text=text, model="fake", input_tokens=0, output_tokens=0, finish="stop")

    # 模拟实现没有需要释放的资源。
    async def close(self) -> None:
        return None
