"""
一次取得项目计划、模块图、开发包、真实测试轮次与操作执行情况。
默认不启动服务和访问数据库；--runs 按需增加最近的数据库运行记录。
"""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi_check.quality.rules import PROJECT
from fastapi_project.development.commands import with_check_directories
from fastapi_project.development.history import read_checks
from fastapi_project.development.runtime import recent_runs
from fastapi_project.development.status import project_status, runtime_progress
from fastapi_project.development.summary import (
    project_summary,
    selected_operation,
    selected_test,
    summary_markdown,
)
from fastapi_project.development.views import module_markdown, project_graph, project_markdown

from app.setup.catalog import MODULES
from shared.config.settings import Settings
from shared.modules.catalog import Catalog


# 参数仅选择查看范围，默认不访问数据库。
def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="查看项目开发状态与设计图")
    parser.add_argument("--module", default="", help="只显示一个模块的步骤、条件和测试情况")
    parser.add_argument(
        "--json", action="store_true", help="输出机器可读状态，配合 --summary 先读摘要"
    )
    parser.add_argument(
        "--summary", action="store_true", help="只读决策摘要，不展开全部步骤和测试运行"
    )
    parser.add_argument(
        "--operation", default="", help="只展开一个完整操作名，例如 customer_contact.create_record"
    )
    parser.add_argument("--test", default="", help="按准确 pytest 测试编号读取最近记录")
    parser.add_argument("--runs", action="store_true", help="只读查询当前配置数据库的近期运行")
    parser.add_argument(
        "--checks",
        action="append",
        type=Path,
        default=[],
        help="同时读取分支 Agent 或 CI 的检查记录目录，可重复指定",
    )
    parser.add_argument("--limit", type=int, default=100, help="最多读取的运行记录，范围 1 到 1000")
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        parser.error("limit 必须在 1 到 1000 之间")
    if sum(bool(value) for value in (args.summary, args.operation, args.test)) > 1:
        parser.error("--summary、--operation、--test 分别选择摘要或具体细节，不能同时使用")
    if (args.operation or args.test) and args.runs:
        parser.error("单操作或单测试查看留存的测试证据；数据库运行请用 --module 模块名 --runs")
    if args.operation:
        owner = args.operation.partition(".")[0]
        if args.module and args.module != owner:
            parser.error("操作不属于指定模块")
        args.module = owner
    return args


# 全局或单模块视图均支持 JSON，供主干 Agent 直接抽取与分配工作。
def main() -> None:
    args = arguments()
    settings = Settings()
    catalog = Catalog(MODULES)
    from fastapi_docs.export_docs import summaries

    for path, text in summaries(catalog, PROJECT).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    status = project_status(catalog, PROJECT, set(settings.disabled_modules), args.checks)
    if args.module and args.module not in status["modules"] and not args.summary:
        raise SystemExit(f"模块尚未登记：{args.module}；未实现的开发包可用 --summary 查看")
    if args.runs:
        from fastapi_project.development.pipelines import overview, refresh

        from shared.db.database import Database

        # 刷新后关闭隔离查询连接，默认摘要继续只读缓存。
        async def refresh_pipelines() -> None:
            database = Database(settings.database_url)
            try:
                await refresh(database, catalog, PROJECT)
            finally:
                await database.close()

        asyncio.run(refresh_pipelines())
        status["pipelines"] = overview(catalog, PROJECT, module=args.module)
        status["runtime"] = asyncio.run(recent_runs(settings, args.limit, args.module))
        runtime_progress(status, set(settings.disabled_modules), args.module)
    status["graph"] = project_graph(status)
    try:
        result = with_check_directories(select_view(status, args), args.checks)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    if args.json or args.operation or args.test:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.summary:
        print(summary_markdown(result))
    else:
        print(module_markdown(result) if args.module else project_markdown(status))


# 摘要与细节分开选择，保留已有全局、模块 JSON 的用法。
def select_view(status: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    if args.summary:
        return project_summary(status, args.module)
    if args.operation:
        return selected_operation(status, args.operation)
    if args.test:
        return selected_test(status, args.test, args.module, read_checks(PROJECT, args.checks))
    return (
        {**status["modules"][args.module], "runtime": status["runtime"]} if args.module else status
    )


if __name__ == "__main__":
    main()
