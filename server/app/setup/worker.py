"""
worker 进程入口：uv run python -m app.setup.worker
与接口进程使用同一份代码和模块目录；收到 SIGTERM 或 Ctrl+C 后不再领取新任务，等待在途任务结束。
使用 SQLite 时只能运行一个 worker；多个 worker 需要 PostgreSQL。
"""

import asyncio
import logging
import signal
from contextlib import suppress

from app.setup.build import build
from shared.config.settings import Settings
from shared.jobs.worker import Worker, WorkerOptions
from shared.logs.setup import setup_logs

log = logging.getLogger("server.jobs")


# 组装服务并运行 worker，直到收到停止信号。
async def serve(settings: Settings) -> None:
    setup_logs(json_lines=settings.env == "production")
    services = build(settings)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGTERM, signal.SIGINT):
        with suppress(NotImplementedError):
            loop.add_signal_handler(name, stop.set)
    options = WorkerOptions(
        concurrency=settings.job_concurrency,
        poll_seconds=settings.job_poll_seconds,
        shutdown_seconds=settings.job_shutdown_seconds,
        record_days=settings.run_record_days,
        managed_retention=settings.operations.retention,
        health_file=settings.job_health_file,
        schedule_org_id=settings.schedule_org_id,
        schedule_org_ids=tuple(settings.schedule_org_ids),
    )
    worker = Worker(services.runtime, services.queue, settings.api_keys, options)
    flushing = None
    if not services.recorder.store.immediate:
        flushing = asyncio.create_task(services.recorder.run_forever())
    digest, concurrency = services.catalog.digest, options.concurrency
    log.info("worker_started digest=%s concurrency=%s", digest, concurrency)
    try:
        await worker.run(stop)
    finally:
        if flushing is not None:
            await services.recorder.stop(flushing)
        await services.close()


# 读取配置并启动 worker。
def main() -> None:
    asyncio.run(serve(Settings()))


if __name__ == "__main__":
    main()
