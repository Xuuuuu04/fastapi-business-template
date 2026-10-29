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


async def read_body(scope: Scope, receive: Receive, send: Send) -> None:
    while True:
        message = await receive()
        if not message.get("more_body", False):
            break
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


async def run_request(
    receive: Receive, *, app: App = read_body, path: str = "/input"
) -> tuple[RequestLimits, list[Message]]:
    limits = RequestLimits(1000, 1, 5000, ("/upload/",), 0.03, 0.1)
    messages: list[Message] = []

    async def send(message: Message) -> None:
        messages.append(message)

    await RequestMiddleware(app, limits)(
        {"type": "http", "path": path, "headers": [], "state": {}}, receive, send
    )
    return limits, messages


@pytest.mark.parametrize("trickle", [False, True])
async def test_body_total_deadline_releases_inflight(trickle: bool) -> None:
    reads = 0

    async def receive() -> dict:
        nonlocal reads
        reads += 1
        await asyncio.sleep(0.005 if trickle else 0.2)
        return {"type": "http.request", "body": b"x", "more_body": True}

    limits, messages = await run_request(receive)
    assert messages[0]["status"] == 408 and limits.inflight == 0
    assert reads < 20 and b"request_timeout" in messages[-1]["body"]


async def test_body_deadline_does_not_limit_finished_response() -> None:
    first = True

    async def receive() -> dict:
        nonlocal first
        if first:
            first = False
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.sleep(0.06)
        return {"type": "http.disconnect"}

    async def stream(scope: Scope, receive: Receive, send: Send) -> None:
        await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        assert (await receive())["type"] == "http.disconnect"
        await send({"type": "http.response.body", "body": b"done"})

    limits, messages = await run_request(receive, app=stream)
    assert [m["status"] for m in messages if m["type"] == "http.response.start"] == [200]
    assert limits.inflight == 0


async def test_upload_has_independent_budget() -> None:
    async def receive() -> dict:
        await asyncio.sleep(0.05)
        return {"type": "http.request", "body": b"x" * 2000, "more_body": False}

    limits, messages = await run_request(receive, path="/upload/file")
    assert messages[0]["status"] == 200 and limits.inflight == 0


async def test_started_response_cannot_be_replaced() -> None:
    async def receive() -> dict:
        return {"type": "http.request", "body": b"x" * 2000, "more_body": False}

    async def early_reply(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await receive()

    with pytest.raises(BodyTooLarge):
        await run_request(receive, app=early_reply)
