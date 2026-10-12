"""
HTTP和WebSocket辅助功能继承同一应用时钟，独立测试应用之间不共享可变时间。
"""

from starlette.types import ASGIApp, Receive, Scope, Send

from shared.timing.clock import Clock
from shared.timing.current import use_clock


# 原生ASGI包裹保留取消与流式语义，不额外读取请求体。
class ClockMiddleware:
    # 服务组装时传入实际时钟，不读取全局产品配置。
    def __init__(self, app: ASGIApp, clock: Clock) -> None:
        self.app, self.clock = app, clock

    # 同一请求、流式输出和子任务都继承应用时间。
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        with use_clock(self.clock):
            await self.app(scope, receive, send)
