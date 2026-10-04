"""
一次取得项目计划、模块图、开发包、真实测试轮次与操作执行情况。
默认不启动服务和访问数据库；--runs 按需增加最近的数据库运行记录。
"""

import argparse
import asyncio
import json
from pathlib import Path

from app.setup.catalog import MODULES
from shared.config.settings import Settings
from shared.modules.catalog import Catalog
from tools.development.runtime import recent_runs
from tools.development.status import project_status, runtime_progress
from tools.development.views import module_markdown, project_graph, project_markdown
from tools.quality.rules import PROJECT


# 参数仅选择查看范围，默认不访问数据库。
def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="查看项目开发状态与设计图")
    parser.add_argument("--module", default="", help="只显示一个模块的步骤、条件和测试情况")
    parser.add_argument("--json", action="store_true", help="输出机器可读的完整状态")
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
    return args


# 全局或单模块视图均支持 JSON，供主干 Agent 直接抽取与分配工作。
def main() -> None:
    args = arguments()
    settings = Settings()
    status = project_status(Catalog(MODULES), PROJECT, set(settings.disabled_modules), args.checks)
    if args.module and args.module not in status["modules"]:
        raise SystemExit(f"模块尚未登记：{args.module}；未实现的开发包请查看全局视图")
    if args.runs:
        status["runtime"] = asyncio.run(recent_runs(settings, args.limit, args.module))
        runtime_progress(status, set(settings.disabled_modules), args.module)
    status["graph"] = project_graph(status)
    result = (
        {**status["modules"][args.module], "runtime": status["runtime"]} if args.module else status
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(module_markdown(result) if args.module else project_markdown(status))


if __name__ == "__main__":
    main()
