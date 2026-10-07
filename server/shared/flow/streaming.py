"""
流式操作的 SSE 输出。队列限制内存占用；断开连接时取消操作并等待数据库回滚。
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import suppress
from typing import TYPE_CHECKING

from shared.access.caller import Caller
from shared.data.models import Data
from shared.errors.framework import StepRuleBroken
from shared.errors.kinds import BusinessError
from shared.modules.contract import Contract

if TYPE_CHECKING:
    from shared.flow.runtime import Runtime


# 执行声明为 stream 的操作并逐条输出 SSE 事件。
async def stream_events[In: Data, Out: Data](
    runtime: "Runtime", item: Contract[In, Out], input: In, *, caller: Caller, request_id: str
) -> AsyncGenerator[bytes, None]:
    if not item.stream:
        raise StepRuleBroken(f"操作 {item.name} 没有声明 stream=True")
    queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue(maxsize=16)

    # 生产者在队列已满时等待客户端消费。
    async def emit(value: str) -> None:
        await queue.put(("chunk", value))

    # 后台执行流程，向客户端报告最终结果或错误。
    async def work() -> None:
        try:
            result = await runtime.run(
                item,
                input,
                caller=caller,
                request_id=request_id,
                emitter=emit,
                on_start=lambda run_id: queue.put_nowait(("start", run_id)),
            )
            await queue.put(("done", result.model_dump_json()))
        except asyncio.CancelledError:
            raise
        except Exception as error:
            message = (
                error.detail if isinstance(error, BusinessError) else "运行失败，请按运行编号排查"
            )
            problem = {
                "code": error.code if isinstance(error, BusinessError) else "internal_error",
                "message": message,
                "run_id": getattr(error, "run_id", ""),
            }
            await queue.put(("error", json.dumps(problem, ensure_ascii=False)))
        # 正常完成或已报告错误后结束；取消时客户端已离开，不能再等待满队列。
        await queue.put(("end", ""))

    task = asyncio.create_task(work())
    try:
        while True:
            kind, value = await queue.get()
            if kind == "end":
                break
            yield event_bytes(kind, value)
    finally:
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError):
            await task


# 按 SSE 格式写出一个事件；开始和分段文本需要先编码成 JSON 字符串。
def event_bytes(kind: str, value: str) -> bytes:
    data = value if kind in ("done", "error") else json.dumps(value, ensure_ascii=False)
    return f"event: {kind}\ndata: {data}\n\n".encode()
