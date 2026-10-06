"""
分层检查：快速调试、多包验收与整批交付完整检查，实际耗时和范围随结果保存。
默认运行完整检查；--module 可重复或使用逗号列表；--quick 仅用于包内调试。
--affected --base 分支根据新旧依赖选择范围；压力和浏览器测试仍需另行执行。
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from fastapi_check.quality.rules import PROJECT, ROOT
from fastapi_project.development.evidence import system_fingerprint
from fastapi_project.development.history import fingerprints, save_check
from fastapi_project.development.selection import (
    Selection,
    module_files,
    module_names,
    select_affected,
    validate_modules,
)

TYPED = ("app", "service", "shared", "../.agents/skills", "deploy")
INTEGRITY = (
    "tests/architecture/test_structure.py::test_import_rules",
    "tests/architecture/test_structure.py::test_registry_is_complete",
    "tests/architecture/test_structure.py::test_migrations_match_tables",
)


# 列出全部检查；类型检查只包含有 Python 文件的目录（未添加业务时 service 可能暂时为空）。
def steps(selection: Selection | None = None) -> list[tuple[str, list[str]]]:
    selection = selection or Selection()
    typed = [name for name in TYPED if any((ROOT / name).rglob("*.py"))]
    tests = ["-m", "pytest", "-q", "--durations=10"]
    for module in selection.modules:
        tests += [f"tests/modules/{module}", f"tests/integration/{module}"]
    if selection.quick:
        files = module_files(selection.modules)
        if not files:
            raise ValueError("快速检查没有可检查的 Python 文件")
        return [
            ("局部代码风格", ["ruff", "check", *files]),
            ("局部代码格式", ["ruff", "format", "--check", *files]),
            ("快速模块测试", tests),
        ]
    if selection.modules:
        tests += list(INTEGRITY)
    return [
        ("代码风格", ["ruff", "check", ".", "../.agents/skills"]),
        ("代码格式", ["ruff", "format", "--check", ".", "../.agents/skills"]),
        ("类型检查", ["mypy", *typed]),
        (
            "生成文档",
            ["../.agents/skills/fastapi-docs/scripts/run_docs.py", "export_docs", "--check"],
        ),
        ("模块测试" if selection.modules else "默认测试", tests),
    ]


# 运行一项检查，返回是否通过。
def run(title: str, command: list[str], env: dict[str, str]) -> bool:
    direct = command[0] == "-m" or command[0].endswith(".py")
    runner = [sys.executable, *command] if direct else [sys.executable, "-m", *command]
    print(f"\n==> {title}：{' '.join(command)}", flush=True)
    return subprocess.run(runner, cwd=ROOT, env=env, check=False).returncode == 0


# 测试结果从 pytest 的结束钩子读取，启动失败时也留下明确失败记录。
def run_tests(
    title: str, command: list[str], env: dict[str, str], database: str
) -> tuple[bool, dict[str, object]]:
    with TemporaryDirectory(prefix="template-check-") as folder:
        result = Path(folder) / "tests.json"
        passed = run(title, command, {**env, "APP_DEVELOPMENT_RESULT": str(result)})
        evidence = (
            json.loads(result.read_text(encoding="utf-8"))
            if result.exists()
            else {"exit_code": 1, "cases": []}
        )
    return passed and evidence["exit_code"] == 0, {"database": database, **evidence}


# 保存每轮的检查结果；检查期间源码改变时，该轮不能证明当前版本。
def execute(selection: Selection, postgres: str) -> list[tuple[str, bool]]:
    from app.setup.catalog import MODULES
    from shared.modules.catalog import Catalog

    started = perf_counter()
    modules = list(selection.modules) or [item.name for item in MODULES]
    links = Catalog(MODULES).links()
    before = fingerprints(PROJECT, modules, links)
    system_before = system_fingerprint(PROJECT)
    env = {**os.environ, "APP_DISABLED_MODULES": "[]", "APP_DEVELOPMENT_REPEAT_DATABASE": "0"}
    env["APP_DEVELOPMENT_MODULES"] = json.dumps([] if selection.quick else list(selection.modules))
    selected = steps(selection)
    timings: dict[str, float] = {}
    results = []
    for title, command in selected[:-1]:
        start = perf_counter()
        results.append((title, run(title, command, env)))
        timings[title] = round(perf_counter() - start, 3)
    database = (
        "postgresql" if env.get("APP_TEST_DATABASE_URL", "").startswith("postgres") else "sqlite"
    )
    start = perf_counter()
    passed, evidence = run_tests(*selected[-1], env, database)
    timings[selected[-1][0]] = round(perf_counter() - start, 3)
    results.append((selected[-1][0], passed))
    suites = [evidence]
    if postgres:
        start = perf_counter()
        passed, evidence = run_tests(
            "PostgreSQL 测试",
            selected[-1][1],
            {
                **env,
                "APP_TEST_DATABASE_URL": postgres,
                "APP_DEVELOPMENT_REPEAT_DATABASE": "1" if passed else "0",
            },
            "postgresql",
        )
        results.append(("PostgreSQL 测试", passed))
        suites.append(evidence)
        timings["PostgreSQL 测试"] = round(perf_counter() - start, 3)
    finish_check(
        selection, before, system_before, modules, links, results, suites, timings, started
    )
    return results


# 版本在执行前后比较，计时包括版本读取；记录不保存连接地址或测试数据。
def finish_check(
    selection: Selection,
    before: dict[str, str],
    system_before: str,
    modules: list[str],
    links: dict[str, dict[str, list[str]]],
    results: list[tuple[str, bool]],
    suites: list[dict[str, object]],
    timings: dict[str, float],
    started: float,
) -> None:
    changed = before != fingerprints(
        PROJECT, modules, links
    ) or system_before != system_fingerprint(PROJECT)
    elapsed = round(perf_counter() - started, 3)
    path = save_check(
        PROJECT,
        {
            "fingerprints": before,
            "scope": selection.scope(),
            "source_changed": changed,
            "system_fingerprint": system_before,
            "passed": all(passed for _, passed in results),
            "checks": dict(results),
            "suites": suites,
            "timings": timings,
            "elapsed_seconds": elapsed,
            "selection_reasons": list(selection.reasons),
        },
    )
    print(f"\n本轮检查记录：{path.relative_to(PROJECT)}")
    print(
        f"本轮耗时：{elapsed:.3f} 秒；"
        + "；".join(f"{title} {seconds:.3f}s" for title, seconds in timings.items())
    )


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
    args = parser.parse_args()
    if args.affected and (args.module or args.quick):
        parser.error("--affected 不能与 --module 或 --quick 同时使用")
    if args.quick and not module_names(args.module):
        parser.error("--quick 必须指定 --module，避免把局部检查误用为完整检查")
    if args.module and not module_names(args.module):
        parser.error("--module 不能为空")
    return args


# 范围选择与实际执行分开；没有改动明确报告未执行，不写一条成功记录。
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
    print(f"检查范围：{'、'.join(selection.modules) or '全部登记模块'}", flush=True)
    if selection.quick:
        print("快速调试：未执行完整类型、生成文档及整合检查，不能代替包验收。", flush=True)
    results = execute(selection, args.postgres)
    print("\n检查结果：")
    for title, passed in results:
        print(f"  {'通过' if passed else '失败'}  {title}")
    if not args.postgres:
        print("  未运行  PostgreSQL 测试（生产使用 PostgreSQL 时，发布前必须加 --postgres 运行）")
    sys.exit(0 if all(passed for _, passed in results) else 1)


if __name__ == "__main__":
    main()
