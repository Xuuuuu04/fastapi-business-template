"""
检查参数与实际执行分开，非法范围在启动子进程前拒绝。
"""

import argparse
import os

from fastapi_project.development.selection import module_names


# 保留两个CPU给主机和嵌套命令，小机器至少两个、大机器最多四个测试进程。
def default_workers() -> int:
    return max(2, min(4, (os.cpu_count() or 2) - 2))


# 依次运行全部检查并汇总结果。
def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="快速调试、分层验收或完整检查")
    parser.add_argument(
        "--module",
        action="append",
        default=[],
        help="指定模块，可重复或用逗号分隔；公共检查只执行一次",
    )
    parser.add_argument(
        "--postgres", default="", help="PostgreSQL 连接地址，用于在真实数据库上再跑测试"
    )
    parser.add_argument(
        "--quick", action="store_true", help="仅局部风格、格式及模块测试，不代替验收"
    )
    parser.add_argument("--affected", action="store_true", help="按改动及新旧依赖检查受影响模块")
    parser.add_argument(
        "--base", default="origin/main", help="--affected 的比较分支，默认 origin/main"
    )
    parser.add_argument(
        "--database", choices=["auto", "sqlite", "postgresql", "both"], default="auto"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=default_workers(),
        help="所有数据库共用的总进程预算，默认按CPU自动设置",
    )
    parser.add_argument(
        "--group", choices=["all", "pure", "module", "flow", "framework"], default="all"
    )
    parser.add_argument("--delivery", action="store_true", help="交付时强制重新执行")
    args = parser.parse_args()
    if not 0 <= args.workers <= 32:
        parser.error("workers应为0至32")
    if args.affected and (args.module or args.quick):
        parser.error("--affected 不能与 --module 或 --quick 同时使用")
    if args.quick and not module_names(args.module):
        parser.error("--quick 必须指定 --module，避免把局部检查误用为完整检查")
    if args.module and not module_names(args.module):
        parser.error("--module 不能为空")
    return args
