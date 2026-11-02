import argparse
import asyncio
import json
import re
import signal
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import FrameType

import uvicorn
from fastapi_check.acceptance_environment import (
    check_isolation,
    create_schema,
    isolated_settings,
    prepare_seed,
)
from fastapi_check.acceptance_lifecycle import lifecycle_path, temporary_folder
from fastapi_check.quality.rules import PROJECT
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.setup.application import application
from app.setup.build import build
from app.setup.web import create_app


class AcceptanceHeader:
    def __init__(self, app: ASGIApp, run_id: str) -> None:
        self.app = app
        self.value = run_id.encode("ascii")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def response(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers = [
                    (key, value) for key, value in headers if key.lower() != b"x-acceptance-run"
                ]
                message = {**message, "headers": [*headers, (b"x-acceptance-run", self.value)]}
            await send(message)

        await self.app(scope, receive, response)


def listen(port: int) -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", port))
        listener.listen(128)
        listener.setblocking(False)
        return listener
    except BaseException:
        listener.close()
        raise


async def serve(listener: socket.socket, folder: Path, run_id: str, seed: bool) -> None:
    specification = application()
    settings = isolated_settings(specification, folder)
    services = build(settings, application=specification)
    entered = False
    try:
        app = create_app(settings, services, application=specification)
        check_isolation(settings, folder)
        async with app.router.lifespan_context(app):
            entered = True
            await create_schema(services)
            if seed:
                await prepare_seed(services, folder, PROJECT)
            wrapped = AcceptanceHeader(app, run_id)
            config = uvicorn.Config(
                wrapped,
                host="127.0.0.1",
                port=listener.getsockname()[1],
                lifespan="off",
                access_log=False,
                log_level="warning",
            )
            print(
                json.dumps(
                    {
                        "event": "acceptance_starting",
                        "run_id": run_id,
                        "port": listener.getsockname()[1],
                        "folder": str(folder),
                        "schema": "metadata",
                        "database": "isolated_sqlite",
                    }
                ),
                flush=True,
            )
            server = uvicorn.Server(config)
            await server.serve(sockets=[listener])
            if not server.started:
                raise RuntimeError("验收服务未能启动")
    finally:
        if not entered:
            await services.close()


def request_stop(number: int, frame: FrameType | None) -> None:
    raise KeyboardInterrupt


@contextmanager
def interrupt_on_terminate() -> Iterator[None]:
    previous = signal.signal(signal.SIGTERM, request_stop)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def main() -> None:
    parser = argparse.ArgumentParser(description="启动本轮隔离 SQLite HTTP 验收服务")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--seed", action="store_true")
    parser.add_argument("--lifecycle-file")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("--port 必须在 0 到 65535 之间；0 由系统分配端口")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", args.run_id):
        parser.error("--run-id 只能包含 1 到 80 个英文字母、数字、下划线或连字符")
    try:
        lifecycle = lifecycle_path(args.lifecycle_file)
        with (
            interrupt_on_terminate(),
            listen(args.port) as listener,
            temporary_folder(args.run_id, lifecycle) as folder,
        ):
            asyncio.run(serve(listener, folder, args.run_id, args.seed))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception as error:
        raise SystemExit(
            f"验收服务启动失败：{type(error).__name__}，请检查端口、配置和种子函数"
        ) from None


if __name__ == "__main__":
    main()
