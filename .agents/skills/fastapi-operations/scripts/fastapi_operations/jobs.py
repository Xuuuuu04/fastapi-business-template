"""
后台任务的人工处理命令：
  list [--state failed]                      列出任务
  show 任务编号                               查看任务
  requeue 任务编号 [--accept-version] --yes   把失败、待检查、等待兼容版本的任务重新排队
  cancel 任务编号 --yes                       取消尚未开始的任务
重新排队可能再次产生外部效果（例如再次发送通知），执行前请确认任务的实际情况；
修改类命令必须加 --yes。
"""

import argparse
import asyncio
from dataclasses import asdict

from app.setup.catalog import MODULES
from shared.config.settings import Settings
from shared.db.database import Database
from shared.jobs.checkpoint_store import list_segments, progress
from shared.jobs.views import cancel, get_job, list_jobs, requeue
from shared.modules.catalog import Catalog


# 执行一个命令。
async def run(args: argparse.Namespace) -> None:
    database = Database(Settings().database_url)
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
            catalog = Catalog(MODULES)
            print(await requeue(database, catalog, args.job_id, accept_version=args.accept_version))
        else:
            print(await cancel(database, args.job_id))
    finally:
        await database.close()


# 定义命令行参数。
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
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
