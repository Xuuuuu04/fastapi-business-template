import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import httpx2

from shared.data.limits import ResponseTooLarge, limited_bytes
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

    async def complete(self, request: ModelRequest) -> ModelReply: ...

    async def close(self) -> None: ...


class OpenAICompatible:
    name = "openai_compatible"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float,
        transport: httpx2.AsyncBaseTransport | None = None,
        max_response_bytes: int = 2_000_000,
    ) -> None:
        self.model = model
        self.max_response_bytes = max_response_bytes
        self.client = httpx2.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )

    async def complete(self, request: ModelRequest) -> ModelReply:
        try:
            async with self.client.stream(
                "POST", "/chat/completions", json=self.body(request)
            ) as response:
                if response.status_code == 429 or response.status_code >= 500:
                    raise ModelUnavailable(f"大模型服务暂时不可用（HTTP {response.status_code}）")
                if response.status_code >= 400:
                    raise ModelRejected(f"大模型服务拒绝请求（HTTP {response.status_code}）")
                content = await limited_bytes(
                    response.aiter_bytes(chunk_size=65536), self.max_response_bytes
                )
        except ResponseTooLarge as error:
            raise ModelRejected("大模型服务返回内容超过上限，请调整输出范围") from error
        except httpx2.TimeoutException as error:
            raise ModelUnavailable("大模型服务响应超时") from error
        except httpx2.TransportError as error:
            raise ModelUnavailable("无法连接大模型服务") from error
        try:
            return self.reply(json.loads(content))
        except ValueError as error:
            raise ModelUnavailable("大模型服务返回的格式无法识别") from error

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

    async def close(self) -> None:
        await self.client.aclose()


Answer = str | Callable[[ModelRequest], str]


class FakeModel:
    name = "fake"

    def __init__(self, replies: Mapping[str, Answer] | None = None) -> None:
        self.replies = dict(replies or {})
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelReply:
        self.requests.append(request)
        answer = self.replies.get(request.prompt, "（本地模拟回复，没有调用真实模型）")
        text = answer(request) if callable(answer) else answer
        return ModelReply(text=text, model="fake", input_tokens=0, output_tokens=0, finish="stop")

    async def close(self) -> None:
        return None
