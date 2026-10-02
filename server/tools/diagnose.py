"""
排查命令，供人和 Agent 在能访问数据库的机器上直接查看，不必先读代码：
  runs [--status failed] [--module 名称]   最近的运行和中文摘要
  run 运行编号                             一次运行的中文排查报告
  flow 操作名                              操作的计算流程图和字段来源（来自声明，不需要数据库）
  field 操作名 字段名                       逐层说明一个字段怎样得出
运行记录保存在进程内存时（APP_RUN_RECORDS=memory），命令行看不到服务进程里的记录，请用排查接口。
"""

import argparse
import asyncio
import time

from app.setup.catalog import MODULES
from shared.config.settings import Settings
from shared.db.database import Database
from shared.graphs.lineage import explain, field_sources
from shared.graphs.observed import run_report
from shared.graphs.static import flow_graph
from shared.modules.catalog import Catalog
from shared.records.stores import RunFilter, SqlRunStore


# 打印最近的运行。
async def show_runs(store: SqlRunStore, status: str, module: str, limit: int) -> None:
    for run in await store.recent(RunFilter(module=module, status=status), limit):
        print(f"{run.id}  {run.status:<8} {run.title}：{run.summary}")


# 打印一次运行的中文排查报告。
async def show_run(store: SqlRunStore, run_id: str) -> None:
    found = await store.get(run_id)
    if found is None:
        print(f"没有找到运行 {run_id} 的记录：可能已过期清理，或者运行记录保存在服务进程内存中")
        return
    print(run_report(await store.tree(found.root_id), run_id))


# 打印数据库中已结束的运行统计。
async def show_stats(store: SqlRunStore, hours: int, module: str) -> None:
    rows = await store.stats(time.time() - hours * 3600, module)
    for row in rows:
        print(
            f"{row['contract']}  {row['status']}  {row['count']} 次  "
            f"平均 {row['average_ms']} 毫秒  最长 {row['max_ms']} 毫秒"
        )
    if not rows:
        print("这个时段没有已保存的运行记录")


# 打印操作的流程图和字段来源。
def show_flow(catalog: Catalog, name: str) -> None:
    binding = catalog.find(name)
    if binding is None:
        print(f"没有登记操作 {name}，可用的操作：{', '.join(sorted(catalog.by_name))}")
        return
    print(f"# {binding.contract.title}（{name}）\n\n```mermaid\n{flow_graph(binding)}\n```\n")
    for source in field_sources(binding).values():
        where = " ".join(part for part in (source.origin, source.step, source.rule) if part)
        print(f"- {source.name}（{source.meaning}）：{where}")


# 打印一个字段的来源说明。
def show_field(catalog: Catalog, name: str, field: str) -> None:
    binding = catalog.find(name)
    if binding is None or field not in binding.types.notes:
        print(f"没有找到操作 {name} 的字段 {field}")
        return
    print("\n".join(explain(binding, field)))


# 解析命令并执行。
async def run(args: argparse.Namespace) -> None:
    catalog = Catalog(MODULES)
    if args.command == "flow":
        show_flow(catalog, args.name)
        return
    if args.command == "field":
        show_field(catalog, args.name, args.field)
        return
    settings = Settings()
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


# 定义命令行参数。
def main() -> None:
    parser = argparse.ArgumentParser(description="查看运行记录、流程和字段来源")
    commands = parser.add_subparsers(dest="command", required=True)
    runs = commands.add_parser("runs", help="最近的运行")
    runs.add_argument("--status", default="")
    runs.add_argument("--module", default="")
    runs.add_argument("--limit", type=int, default=20)
    stats = commands.add_parser("stats", help="按操作统计已结束的运行")
    stats.add_argument("--hours", type=int, default=24)
    stats.add_argument("--module", default="")
    commands.add_parser("run", help="一次运行的报告").add_argument("run_id")
    commands.add_parser("flow", help="操作的流程").add_argument("name")
    field = commands.add_parser("field", help="字段来源")
    field.add_argument("name")
    field.add_argument("field")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
