import argparse
import json
import os
import subprocess
import sys

from fastapi_check.development_rules import check_development
from fastapi_check.quality.rules import ROOT
from fastapi_project.development.selection import (
    Selection,
    module_files,
    module_names,
    select_affected,
    validate_modules,
)

TYPED = ("app", "service", "library", "shared", "../.agents/skills", "devtools/src")
INTEGRITY = (
    "tests/architecture/test_structure.py::test_import_rules",
    "tests/architecture/test_structure.py::test_registry_is_complete",
    "tests/architecture/test_structure.py::test_migrations_match_tables",
)
QUALITY = "tests/quality/test_project_quality.py"
NEXT_STEPS = {
    "迁移表归属": "请按上方列出的表补充归属登记",
    "实现状态": "交付前把模拟步骤换成真实实现并设置 simulated=False",
    "代码风格": "请对上方列出的文件运行 uv run ruff check --fix，再处理剩余问题",
    "代码格式": "请对上方列出的文件运行 uv run ruff format",
    "类型检查": "请按上方 mypy 输出修正类型",
    "接口文档": "openapi.json 已过期，请运行 uv run dev docs",
}
SYSTEM_ENVIRONMENT = {
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "TMPDIR",
    "TMP",
    "TEMP",
    "LANG",
    "TZ",
    "SYSTEMROOT",
    "WINDIR",
    "PYTHONPATH",
    "PYTHONUNBUFFERED",
    "PYTHONDONTWRITEBYTECODE",
    "UV_CACHE_DIR",
    "APP_TEST_REDIS_URL",
    "APP_TEST_S3_ENDPOINT",
    "APP_TEST_S3_ACCESS_KEY",
    "APP_TEST_S3_SECRET_KEY",
    "APP_TEST_S3_BUCKET",
    "APP_TEST_S3_REGION",
}


def default_workers() -> int:
    return max(2, min(4, (os.cpu_count() or 2) - 2))


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="静态检查加测试")
    parser.add_argument(
        "--module", action="append", default=[], help="指定模块，可重复或用逗号分隔"
    )
    parser.add_argument(
        "--quick", action="store_true", help="只查所选模块的风格、格式、质量规则和测试"
    )
    parser.add_argument("--affected", action="store_true", help="按和 --base 的差异选出受影响模块")
    parser.add_argument("--base", default="origin/main", help="--affected 的比较分支")
    parser.add_argument("--postgres", default="", help="测试改用这个隔离 PostgreSQL 控制地址")
    parser.add_argument("--workers", type=int, default=default_workers(), help="测试进程数")
    parser.add_argument(
        "--group", choices=["all", "pure", "module", "flow", "framework"], default="all"
    )
    parser.add_argument("--delivery", action="store_true", help="交付检查，不允许模拟步骤")
    args = parser.parse_args()
    if not 0 <= args.workers <= 32:
        parser.error("workers应为0至32")
    if args.affected and (args.module or args.quick):
        parser.error("--affected 不能与 --module 或 --quick 同时使用")
    if args.quick and not module_names(args.module):
        parser.error("--quick 必须指定 --module")
    return args


def steps(selection: Selection) -> list[tuple[str, list[str]]]:
    tests = ["-m", "pytest", "-q", "--durations=10"]
    for module in selection.modules:
        tests += [f"tests/modules/{module}", f"tests/integration/{module}"]
    files = module_files(selection.modules) if selection.modules else [".", "../.agents/skills"]
    if not files:
        raise ValueError("所选模块没有可检查的 Python 文件")
    if selection.quick:
        return [
            ("代码风格", ["ruff", "check", *files]),
            ("代码格式", ["ruff", "format", "--check", *files]),
            ("模块测试", [*tests, QUALITY]),
        ]
    if selection.modules:
        tests += [*INTEGRITY, QUALITY]
    typed = [name for name in TYPED if any((ROOT / name).rglob("*.py"))]
    return [
        ("代码风格", ["ruff", "check", *files]),
        ("代码格式", ["ruff", "format", "--check", *files]),
        ("类型检查", ["mypy", *typed]),
        ("接口文档", ["-m", "fastapi_dev.main", "docs", "--check"]),
        ("模块测试" if selection.modules else "测试", tests),
    ]


def environment(
    selection: Selection, postgres: str, workers: int, group: str, delivery: bool
) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key in SYSTEM_ENVIRONMENT or key.startswith("LC_")
    }
    env |= {
        "APP_TEST_GROUP": group,
        "APP_TEST_WORKERS": str(workers),
        "APP_DEVELOPMENT_DELIVERY": "1" if delivery else "0",
        "APP_DEVELOPMENT_MODULES": json.dumps(list(selection.modules)),
        "APP_DISABLED_MODULES": "[]",
    }
    if postgres:
        env["APP_TEST_CONTROL_URL"] = postgres
    return env


def run(title: str, command: list[str], env: dict[str, str]) -> bool:
    direct = command[0] == "-m"
    runner = [sys.executable, *command] if direct else [sys.executable, "-m", *command]
    print(f"\n==> {title}：{' '.join(command)}", flush=True)
    return subprocess.run(runner, cwd=ROOT, env=env, check=False).returncode == 0


def migration_check() -> bool:
    from app.setup.application import application
    from app.setup.catalog import MODULES
    from shared.db.ownership import check_migrations

    errors = check_migrations(ROOT, MODULES, application().settings("test"))
    for error in errors:
        print(error, flush=True)
    return not errors


def execute(
    selection: Selection, postgres: str, workers: int, group: str, delivery: bool
) -> list[tuple[str, bool]]:
    env = environment(selection, postgres, workers, group, delivery)
    results = [("迁移表归属", migration_check()), ("实现状态", not check_development(delivery))]
    selected = steps(selection)
    for title, command in selected[:-1]:
        results.append((title, run(title, command, env)))
    title, tests = selected[-1]
    if workers:
        tests = [*tests, "--dist=load", "--maxschedchunk=2", "-n", str(workers)]
    results.append((title, run(title, tests, env)))
    return results


def main() -> None:
    from app.setup.catalog import MODULES
    from shared.modules.catalog import Catalog

    args = arguments()
    catalog = Catalog(MODULES)
    try:
        selection = (
            select_affected(catalog, args.base)
            if args.affected
            else Selection(module_names(args.module), args.quick)
        )
        validate_modules(selection.modules, catalog)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    for reason in selection.reasons:
        print(reason, flush=True)
    if selection.unchanged:
        return
    print(f"检查范围：{'、'.join(selection.modules) or '全部模块'}", flush=True)
    results = execute(selection, args.postgres, args.workers, args.group, args.delivery)
    print("\n检查结果：")
    for title, passed in results:
        print(f"  {'通过' if passed else '失败'}  {title}")
        if not passed and title in NEXT_STEPS:
            print(f"        {NEXT_STEPS[title]}")
    sys.exit(0 if all(passed for _, passed in results) else 1)


if __name__ == "__main__":
    main()
