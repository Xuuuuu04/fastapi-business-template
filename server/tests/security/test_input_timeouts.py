"""
正文期限按输入总耗时计算，超时释放请求额度，长响应不受正文期限限制。
"""

import asyncio

import pytest

from app.api.middleware import (
    App,
    BodyTooLarge,
    Message,
    Receive,
    RequestLimits,
    RequestMiddleware,
    Scope,
    Send,
)

pytestmark = pytest.mark.anyio


# 完整读取请求正文后再回复，模拟真实输入解析阶段。
async def read_body(scope: Scope, receive: Receive, send: Send) -> None:
    while True:
        message = await receive()
        if not message.get("more_body", False):
            break
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


# 收集真实中间件输出，不依赖后台服务或数据库。
async def run_request(
    receive: Receive, *, app: App = read_body, path: str = "/input"
) -> tuple[RequestLimits, list[Message]]:
    limits = RequestLimits(1000, 1, 5000, ("/upload/",), 0.03, 0.1)
    messages: list[Message] = []

    # 保存响应消息以检查状态与重复响应。
    async def send(message: Message) -> None:
        messages.append(message)

    await RequestMiddleware(app, limits)(
        {"type": "http", "path": path, "headers": [], "state": {}}, receive, send
    )
    return limits, messages


# 慢首块和不断发送少量内容都不能无限延长占用时间。
@pytest.mark.parametrize("trickle", [False, True])
async def test_body_total_deadline_releases_inflight(trickle: bool) -> None:
    reads = 0

    # 合成持续慢输入；涓滴输入也一直没有完成正文。
    async def receive() -> dict:
        nonlocal reads
        reads += 1
        await asyncio.sleep(0.005 if trickle else 0.2)
        return {"type": "http.request", "body": b"x", "more_body": True}

    limits, messages = await run_request(receive)
    assert messages[0]["status"] == 408 and limits.inflight == 0
    assert reads < 20 and b"request_timeout" in messages[-1]["body"]


# 已读取完成的正文不会把长响应和断开监听变成输入超时。
async def test_body_deadline_does_not_limit_finished_response() -> None:
    first = True

    # 正文立刻完成，之后的断开监听可以比正文期限更长。
    async def receive() -> dict:
        nonlocal first
        if first:
            first = False
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.sleep(0.06)
        return {"type": "http.disconnect"}

    # 持续响应使用同一个 receive，不应被正文期限取消。
    async def stream(scope: Scope, receive: Receive, send: Send) -> None:
        await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        assert (await receive())["type"] == "http.disconnect"
        await send({"type": "http.response.body", "body": b"done"})

    limits, messages = await run_request(receive, app=stream)
    assert [m["status"] for m in messages if m["type"] == "http.response.start"] == [200]
    assert limits.inflight == 0


# 上传有独立大小和总期限，允许普通输入不能接受的合法文件。
async def test_upload_has_independent_budget() -> None:
    # 合成请求输入或提前响应，用于验证资源与响应协议。
    async def receive() -> dict:
        await asyncio.sleep(0.05)
        return {"type": "http.request", "body": b"x" * 2000, "more_body": False}

    limits, messages = await run_request(receive, path="/upload/file")
    assert messages[0]["status"] == 200 and limits.inflight == 0


# 响应已开始后输入超限，关闭该请求，不发送第二个响应头。
async def test_started_response_cannot_be_replaced() -> None:
    # 合成请求输入或提前响应，用于验证资源与响应协议。
    async def receive() -> dict:
        return {"type": "http.request", "body": b"x" * 2000, "more_body": False}

    # 合成请求输入或提前响应，用于验证资源与响应协议。
    async def early_reply(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await receive()

    with pytest.raises(BodyTooLarge):
        await run_request(receive, app=early_reply)
