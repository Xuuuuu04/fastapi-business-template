import argparse
import asyncio
import json
import time
from typing import Literal

from app.setup.application import application, application_modules
from shared.db.database import Database
from shared.graphs.lineage import explain, field_sources
from shared.graphs.observed import run_report
from shared.graphs.static import flow_graph
from shared.modules.catalog import Catalog
from shared.records.stores import RunFilter, SqlRunStore
from shared.timing.budgets import budget_report


async def show_runs(store: SqlRunStore, status: str, module: str, limit: int) -> None:
    for run in await store.recent(RunFilter(module=module, status=status), limit):
        print(f"{run.id}  {run.status:<8} {run.title}：{run.summary}")


async def show_run(store: SqlRunStore, run_id: str) -> None:
    found = await store.get(run_id)
    if found is None:
        print(f"没有找到运行编号 {run_id} 的记录：记录可能已过期删除，或只保存在服务进程的内存中")
        return
    print(run_report(await store.tree(found.root_id), run_id))


async def show_stats(store: SqlRunStore, hours: int, module: str) -> None:
    rows = await store.stats(time.time() - hours * 3600, module)
    for row in rows:
        print(
            f"{row['contract']}  {row['status']}  {row['count']} 次  "
            f"平均 {row['average_ms']} 毫秒  最长 {row['max_ms']} 毫秒"
        )
    if not rows:
        print("这个时段没有已保存的运行记录")


def show_flow(catalog: Catalog, name: str) -> None:
    binding = catalog.find(name)
    if binding is None:
        print(f"没有登记操作 {name}，可用的操作：{', '.join(sorted(catalog.by_name))}")
        return
    print(f"# {binding.contract.title}（{name}）\n\n```mermaid\n{flow_graph(binding)}\n```\n")
    for source in field_sources(binding).values():
        where = " ".join(part for part in (source.origin, source.step) if part)
        print(f"- {source.name}（{source.meaning}）：{where}")


def show_field(catalog: Catalog, name: str, field: str) -> None:
    binding = catalog.find(name)
    if binding is None or field not in binding.types.notes:
        print(f"没有找到操作 {name} 的字段 {field}")
        return
    print("\n".join(explain(binding, field)))


async def run(args: argparse.Namespace) -> None:
    catalog = Catalog(application_modules())
    if args.command == "budgets":
        mode: Literal["runtime", "offline"] = "runtime" if args.runtime_config else "offline"
        report = budget_report(catalog, application().settings(mode))
        report["configuration"] = "实际运行配置" if args.runtime_config else "不连接服务的默认配置"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    if args.command == "flow":
        show_flow(catalog, args.name)
        return
    if args.command == "field":
        show_field(catalog, args.name, args.field)
        return
    settings = application().settings()
    if settings.run_records != "database":
        print("提示：当前配置 APP_RUN_RECORDS=memory，服务进程的记录不在数据库中。")
    database = Database(settings.database_url)
    try:
        store = SqlRunStore(database)
        if args.command == "runs":
            await show_runs(store, args.status, args.module, args.limit)
        elif args.command == "stats":
            await show_stats(store, args.hours, args.module)
        else:
            await show_run(store, args.run_id)
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="查看运行记录、流程和字段来源")
    commands = parser.add_subparsers(dest="command", required=True)
    budgets = commands.add_parser("budgets", help="查看超时时间及其配置位置，不访问数据库")
    budgets.add_argument(
        "--runtime-config", action="store_true", help="读取当前运行配置中的超时时间"
    )
    runs = commands.add_parser("runs", help="查看最近的运行记录")
    runs.add_argument("--status", default="")
    runs.add_argument("--module", default="")
    runs.add_argument("--limit", type=int, default=20)
    stats = commands.add_parser("stats", help="按操作统计已结束的运行")
    stats.add_argument("--hours", type=int, default=24)
    stats.add_argument("--module", default="")
    commands.add_parser("run", help="查看一次运行的报告").add_argument("run_id")
    commands.add_parser("flow", help="查看操作的执行步骤").add_argument("name")
    field = commands.add_parser("field", help="字段来源")
    field.add_argument("name")
    field.add_argument("field")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
