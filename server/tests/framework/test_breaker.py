"""
连续失败后暂停调用：连续失败达到次数后暂停调用，暂停期间直接失败、不再访问对方；暂停结束后放行一次试探，
试探成功恢复，失败再暂停；对方明确拒绝不算失败。
"""

import httpx2
import pytest

from shared.errors.framework import RemoteRejected, RemoteUnavailable
from shared.records.models import RemoteCallRecord
from shared.remote_calls.breaker import Breaker
from shared.remote_calls.remote import Remote, RemoteConfig
from shared.remote_calls.service import RemoteRequest, RemoteService


# 测试可手动推进的时间，验证暂停调用后的恢复条件。
class Clock:
    # 可以手动拨动的时钟。
    def __init__(self) -> None:
        self.now = 100.0

    # 返回当前时间。
    def __call__(self) -> float:
        return self.now


# 连续失败 3 次后暂停；暂停结束放行一次试探；试探失败再暂停，试探成功恢复。
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


# 明确拒绝说明对方可用，连续失败次数清零；之后连续 5 次暂时故障，再调用就不再访问对方。
@pytest.mark.anyio
async def test_remote_calls_stop_after_failures() -> None:
    seen: list[str] = []

    # /bad 一直返回 503，/rejected 返回 400。
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
                await service.send(target, RemoteRequest("GET", "/bad"), records)
        with pytest.raises(RemoteRejected):
            await service.send(target, RemoteRequest("GET", "/rejected"), records)
        for _ in range(7):
            with pytest.raises(RemoteUnavailable):
                await service.send(target, RemoteRequest("GET", "/bad"), records)
        assert len(seen) == 4 + 1 + 5
        assert "暂停调用" in records[-1].error
    finally:
        await service.close()
