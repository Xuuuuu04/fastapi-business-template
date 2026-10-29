import asyncio
import sys
import time
from pathlib import Path

from app.setup.build import build
from shared.jobs.worker import Worker, WorkerOptions
from tests.framework.segment_sample import module
from tests.testing_app import make_settings


async def run(folder: Path, url: str) -> None:
    services = build(make_settings(folder, database_url=url), modules=[module])
    try:
        ticket = await services.queue.claim(time.time())
        assert ticket is not None
        worker = Worker(services.runtime, services.queue, [], WorkerOptions())
        await worker.execute(ticket)
    finally:
        await services.close()


if __name__ == "__main__":
    asyncio.run(run(Path(sys.argv[1]), sys.argv[2]))
