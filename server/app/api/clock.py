from starlette.types import ASGIApp, Receive, Scope, Send

from shared.timing.clock import Clock
from shared.timing.current import use_clock


class ClockMiddleware:
    def __init__(self, app: ASGIApp, clock: Clock) -> None:
        self.app, self.clock = app, clock

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        with use_clock(self.clock):
            await self.app(scope, receive, send)
