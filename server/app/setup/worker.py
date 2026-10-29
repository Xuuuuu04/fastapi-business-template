import asyncio
import logging
import signal
from contextlib import suppress

from app.setup.application import application as declared_application
from app.setup.build import Services, build
from shared.application.spec import ApplicationSpec, WorkerSpec
from shared.config.settings import Settings
from shared.jobs.worker import Worker, WorkerOptions
from shared.logs.setup import setup_logs

log = logging.getLogger("server.jobs")


async def serve(settings: Settings, *, application: ApplicationSpec | None = None) -> None:
    specification = application or declared_application()
    settings = specification.prepare(settings)
    setup_logs(json_lines=settings.env == "production")
    services = build(settings, application=specification)
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
        health_file=settings.job_health_file,
        schedule_org_id=settings.schedule_org_id,
        schedule_org_ids=tuple(settings.schedule_org_ids),
    )
    worker = Worker(services.runtime, services.queue, settings.api_keys, options)
    flushing = None
    if not services.recorder.store.immediate:
        flushing = asyncio.create_task(services.recorder.run_forever())
    log.info("worker_started concurrency=%s", options.concurrency)
    try:
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(worker.run(stop), name="jobs")
            for extension in specification.workers:
                tasks.create_task(run_extension(extension, services, stop), name=extension.name)
    finally:
        if flushing is not None:
            await services.recorder.stop(flushing)
        await services.close()


async def run_extension(extension: WorkerSpec, services: Services, stop: asyncio.Event) -> None:
    await extension.run(services, stop)


def main() -> None:
    asyncio.run(serve(declared_application().settings()))


if __name__ == "__main__":
    main()
