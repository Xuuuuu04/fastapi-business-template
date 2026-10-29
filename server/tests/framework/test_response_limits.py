import gzip
from collections.abc import AsyncIterator

import httpx2
import pytest

from shared.errors.framework import ModelRejected, RemoteRejected, RemoteResultUnknown
from shared.model_calls.providers import ModelRequest, OpenAICompatible
from shared.remote_calls.remote import RemoteConfig, remote
from shared.remote_calls.service import RemoteRequest, RemoteService

pytestmark = pytest.mark.anyio


class ChunkStream(httpx2.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks, self.reads, self.closed = chunks, 0, False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            self.reads += 1
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.parametrize("method,error", [("GET", RemoteRejected), ("POST", RemoteResultUnknown)])
async def test_chunked_response_stops_at_limit(method: str, error: type[Exception]) -> None:
    stream = ChunkStream([b"x" * 65536] * 8)
    calls = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(200, stream=stream, headers={"Content-Length": "1"})

    service = RemoteService(
        {"partner": RemoteConfig(base_url="https://partner.test", max_response_bytes=80_000)},
        {"partner": httpx2.MockTransport(handle)},
        retry_waits=(0, 0),
    )
    try:
        with pytest.raises(error):
            await service.send(
                remote("partner", "合作方"),
                RemoteRequest(
                    method, "/data", "partner.data", "read" if method == "GET" else "write"
                ),
                [],
            )
        assert stream.reads < 8 and stream.closed and len(calls) == 1
    finally:
        await service.close()


async def test_compressed_model_response_is_limited_after_decompression() -> None:
    stream = ChunkStream([gzip.compress(b"x" * 200_000)])
    transport = httpx2.MockTransport(
        lambda request: httpx2.Response(
            200,
            stream=stream,
            headers={"Content-Encoding": "gzip", "Content-Type": "application/json"},
        )
    )
    provider = OpenAICompatible(
        "https://model.test",
        "synthetic-key",
        "model",
        5,
        transport=transport,
        max_response_bytes=80_000,
    )
    try:
        with pytest.raises(ModelRejected, match="超过上限"):
            await provider.complete(ModelRequest("p", "", "输入", 100, 0.2, False))
        assert stream.closed
    finally:
        await provider.close()


async def test_small_external_json_preserves_reply_contract() -> None:
    service = RemoteService(
        {"partner": RemoteConfig(base_url="https://partner.test")},
        {"partner": httpx2.MockTransport(lambda request: httpx2.Response(200, json={"price": 12}))},
    )
    try:
        reply = await service.send(
            remote("partner", "合作方"), RemoteRequest("GET", "/price", "partner.price", "read"), []
        )
        assert reply.data == {"price": 12} and b"12" in reply.content and "12" in reply.text
    finally:
        await service.close()
