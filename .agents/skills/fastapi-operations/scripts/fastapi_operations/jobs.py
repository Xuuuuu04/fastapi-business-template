import argparse
import asyncio
from dataclasses import asdict

from app.setup.application import application, application_modules
from shared.db.database import Database
from shared.jobs.checkpoint_store import list_segments, progress
from shared.jobs.limits import ResourceLimit
from shared.jobs.resources import reconfigure
from shared.jobs.views import cancel, get_job, list_jobs, requeue
from shared.modules.catalog import Catalog
from shared.timing.current import now


async def run(args: argparse.Namespace) -> None:
    database = Database(application().settings().database_url)
    try:
        if args.command == "list":
            for job in await list_jobs(database, state=args.state, limit=args.limit):
                print(
                    f"{job.id}  {job.state_text:<8} {job.contract}  "
                    f"第 {job.attempt} 次  {job.error_message}"
                )
        elif args.command == "show":
            found = await get_job(database, args.job_id)
            print(asdict(found) if found else "任务不存在")
            if found and (checkpoint := await progress(database, found.id)) is not None:
                print(checkpoint)
        elif args.command == "segments":
            print(await list_segments(database, args.job_id, after=args.after, limit=args.limit))
        elif not args.yes:
            print("修改任务状态需要加 --yes 确认")
        elif args.command == "requeue":
            catalog = Catalog(application_modules())
            print(await requeue(database, catalog, args.job_id, accept_version=args.accept_version))
        elif args.command == "resource":
            async with database.write() as connection:
                await reconfigure(connection, ResourceLimit(args.name, args.capacity), now())
            print("资源额度已调整；请使用匹配声明启动worker")
        else:
            print(await cancel(database, args.job_id))
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="查看和人工处理后台任务")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="列出任务")
    listing.add_argument("--state", default="")
    listing.add_argument("--limit", type=int, default=50)
    commands.add_parser("show", help="查看任务").add_argument("job_id")
    segments = commands.add_parser("segments", help="查看已提交段的行数、耗时和运行编号")
    segments.add_argument("job_id")
    segments.add_argument("--after", type=int, default=0)
    segments.add_argument("--limit", type=int, choices=range(1, 201), default=50)
    again = commands.add_parser("requeue", help="重新排队")
    again.add_argument("job_id")
    again.add_argument("--accept-version", action="store_true")
    again.add_argument("--yes", action="store_true")
    stop = commands.add_parser("cancel", help="取消尚未开始的任务")
    stop.add_argument("job_id")
    stop.add_argument("--yes", action="store_true")
    resource = commands.add_parser("resource", help="无在途尝试时明确调整资源额度")
    resource.add_argument("name")
    resource.add_argument("--capacity", type=int, required=True)
    resource.add_argument("--yes", action="store_true")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
