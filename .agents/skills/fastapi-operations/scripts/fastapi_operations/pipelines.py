import argparse
import asyncio
import json
from typing import Any

from app.setup.application import application, application_modules
from shared.db.database import Database
from shared.modules.catalog import Catalog
from shared.pipelines.member_views import listing as list_members
from shared.pipelines.recovery import resume
from shared.pipelines.views import detail, list_runs


async def run(args: argparse.Namespace) -> None:
    database = Database(application().settings().database_url)
    result: Any
    try:
        if args.command == "list":
            result = await list_runs(database, org_id=args.org, limit=args.limit)
        elif args.command == "show":
            result = await detail(database, args.run_id)
        elif args.command == "members":
            result = await list_members(
                database, args.run_id, args.stage, after=args.after, limit=args.limit
            )
        elif not args.yes:
            result = "恢复需加--yes；请先查看失败阶段及外部实际结果"
        else:
            result = await resume(
                database,
                Catalog(application_modules()),
                args.run_id,
                accept_schema=args.accept_schema,
                confirm_unknown=args.confirm_unknown,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="查看和恢复多阶段业务流程")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list")
    listing.add_argument("--org", default="*")
    listing.add_argument("--limit", type=int, choices=range(1, 201), default=50)
    commands.add_parser("show").add_argument("run_id")
    members = commands.add_parser("members")
    members.add_argument("run_id")
    members.add_argument("stage")
    members.add_argument("--after", default="")
    members.add_argument("--limit", type=int, choices=range(1, 201), default=50)
    recovery = commands.add_parser("resume")
    recovery.add_argument("run_id")
    recovery.add_argument("--accept-schema", action="store_true")
    recovery.add_argument("--confirm-unknown", action="store_true")
    recovery.add_argument("--yes", action="store_true")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
