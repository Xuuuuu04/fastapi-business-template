import httpx2
import pytest

from shared.errors.framework import RemoteRejected, RemoteUnavailable
from shared.records.models import RemoteCallRecord
from shared.remote_calls.breaker import Breaker
from shared.remote_calls.remote import Remote, RemoteConfig
from shared.remote_calls.service import RemoteRequest, RemoteService


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_breaker_states() -> None:
    clock = Clock()
    breaker = Breaker(threshold=3, cooldown=10.0, clock=clock)
    for _ in range(3):
        assert breaker.blocked() == 0
        breaker.failed()
    assert breaker.blocked() == 10.0
    clock.now += 10
    assert breaker.blocked() == 0
    assert breaker.blocked() > 0
    breaker.failed()
    assert breaker.blocked() == 10.0
    clock.now += 10
    assert breaker.blocked() == 0
    breaker.succeeded()
    assert breaker.blocked() == 0 and breaker.state() == "正常"


@pytest.mark.anyio
async def test_remote_calls_stop_after_failures() -> None:
    seen: list[str] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.url.path)
        return httpx2.Response(400 if request.url.path == "/rejected" else 503)

    target = Remote("upstream", "上游", retries=0)
    service = RemoteService(
        {"upstream": RemoteConfig(base_url="https://example.com")},
        {"upstream": httpx2.MockTransport(respond)},
        retry_waits=(),
    )
    records: list[RemoteCallRecord] = []
    try:
        for _ in range(4):
            with pytest.raises(RemoteUnavailable):
                await service.send(
                    target, RemoteRequest("GET", "/bad", "partner.bad", "read"), records
                )
        with pytest.raises(RemoteRejected):
            await service.send(
                target, RemoteRequest("GET", "/rejected", "partner.rejected", "read"), records
            )
        for _ in range(7):
            with pytest.raises(RemoteUnavailable):
                await service.send(
                    target, RemoteRequest("GET", "/bad", "partner.bad", "read"), records
                )
        assert len(seen) == 4 + 1 + 5
        assert "暂停调用" in records[-1].error
    finally:
        await service.close()
