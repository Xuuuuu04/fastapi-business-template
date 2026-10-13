"""
分层检查：快速调试、多包验收与整批交付完整检查，实际耗时和范围随结果保存。
默认运行完整检查；--module 可重复或使用逗号列表；--quick 仅用于包内调试。
--affected --base 分支根据新旧依赖选择范围；压力和浏览器测试仍需另行执行。
"""

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from fastapi_check.arguments import arguments
from fastapi_check.cache import cached_round, execution_profile
from fastapi_check.development_rules import check_development
from fastapi_check.matrix import CheckOptions, clean_environment, databases, execute_matrix
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

TYPED = ("app", "service", "library", "shared", "../.agents/skills", "devtools/src", "deploy")
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
    actual = evidence.get("database", database)
    return passed and evidence["exit_code"] == 0 and actual == database, {
        "database": actual,
        **evidence,
    }


# 迁移历史与启动使用同一检查，旧产品默认提醒。
def migration_check() -> bool:
    from app.setup.application import application
    from app.setup.catalog import MODULES
    from shared.db.ownership import check_migrations

    errors = check_migrations(ROOT, MODULES, application().settings("test"))
    for error in errors:
        print(error, flush=True)
    return not errors


# 保存每轮的检查结果；检查期间源码改变时，该轮不能证明当前版本。
def execute(
    selection: Selection, postgres: str, options: CheckOptions | None = None
) -> list[tuple[str, bool]]:
    from tests.check_profile import product_framework_unchanged

    options = options or CheckOptions()
    matrix = databases(postgres, options.database)
    if (
        not options.delivery
        and options.group != "framework"
        and product_framework_unchanged(PROJECT)
    ):
        print(
            "框架未改动，沿用模板验证（省略模板工具测试，保留业务与框架运行安全测试）",
            flush=True,
        )
    started = perf_counter()
    modules, links, before, system_before = check_versions(selection)
    profile = execution_profile(options, postgres)
    scope: dict[str, object] = (
        selection.scope()
        if options.group == "all"
        else {
            "kind": "group",
            "group": options.group,
            "modules": modules,
        }
    )
    if not options.delivery:
        cached = cached_round(PROJECT, before, system_before, scope, profile)
        if cached:
            print(f"沿用检查 {cached['id']}（{cached['finished_at']}），没有重新执行")
            return list(cached["checks"].items())
    env = check_environment(selection, postgres, options)
    selected = steps(selection)
    results, timings = run_static_checks(selected, env)
    outcomes = execute_matrix(
        matrix, postgres, selected[-1][1], env, options, run_tests, selected[-1][0]
    )
    suites = []
    for database, passed, evidence, seconds in outcomes:
        title = "PostgreSQL 测试" if database == "postgresql" else selected[-1][0]
        results.append((title, passed))
        suites.append(evidence)
        timings[title] = seconds
    finish_check(
        selection,
        before,
        system_before,
        modules,
        links,
        results,
        suites,
        timings,
        started,
        options,
        profile,
        scope,
    )
    return results


# 风格、类型、文档与迁移归属只执行一遍，数据库矩阵共用结果。
def run_static_checks(
    selected: list[tuple[str, list[str]]], env: dict[str, str]
) -> tuple[list[tuple[str, bool]], dict[str, float]]:
    timings: dict[str, float] = {}
    results = [
        ("迁移表归属", migration_check()),
        ("规则与实现状态", check_development(env.get("APP_DEVELOPMENT_DELIVERY") == "1")),
    ]
    for title, command in selected[:-1]:
        start = perf_counter()
        results.append((title, run(title, command, env)))
        timings[title] = round(perf_counter() - start, 3)
    return results, timings


# 模块、依赖实现和完整框架指纹一起参与检查版本。
def check_versions(
    selection: Selection,
) -> tuple[list[str], dict[str, dict[str, list[str]]], dict[str, str], str]:
    from app.setup.application import application_modules
    from shared.modules.catalog import Catalog

    registered = application_modules()
    modules = list(selection.modules) or [item.name for item in registered]
    links = Catalog(registered).links()
    return modules, links, fingerprints(PROJECT, modules, links), system_fingerprint(PROJECT)


# 测试环境明确选择数据库，产品策略从隔离配置读取。
def check_environment(
    selection: Selection, postgres: str, options: CheckOptions | None = None
) -> dict[str, str]:
    from app.setup.application import application

    options = options or CheckOptions()
    env = {
        **clean_environment(),
        "APP_TEST_GROUP": options.group,
        "APP_DEVELOPMENT_DELIVERY": "1" if options.delivery else "0",
        "APP_DISABLED_MODULES": "[]",
        "APP_DEVELOPMENT_REPEAT_DATABASE": "0",
    }
    if postgres:
        env.pop("APP_TEST_DATABASE_URL", None)
    env["APP_MODULE_DEPENDENCIES_STRICT"] = str(
        application().settings("test").module_dependencies_strict
    ).lower()
    env["APP_DEVELOPMENT_MODULES"] = json.dumps([] if selection.quick else list(selection.modules))
    return env


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
    options: CheckOptions | None = None,
    profile: dict[str, object] | None = None,
    scope: dict[str, object] | None = None,
) -> None:
    changed = before != fingerprints(
        PROJECT, modules, links
    ) or system_before != system_fingerprint(PROJECT)
    elapsed = round(perf_counter() - started, 3)
    path = save_check(
        PROJECT,
        {
            "fingerprints": before,
            "scope": scope or selection.scope(),
            "source_changed": changed,
            "system_fingerprint": system_before,
            "passed": all(passed for _, passed in results),
            "checks": dict(results),
            "suites": suites,
            "timings": timings,
            "elapsed_seconds": elapsed,
            "selection_reasons": list(selection.reasons),
            "execution_profile": profile or {},
        },
    )
    print(f"\n本轮检查记录：{path.relative_to(PROJECT)}")
    print(
        f"本轮耗时：{elapsed:.3f} 秒；"
        + "；".join(f"{title} {seconds:.3f}s" for title, seconds in timings.items())
    )


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
    results = execute(
        selection,
        args.postgres,
        CheckOptions(args.database, args.workers, args.group, args.delivery),
    )
    print("\n检查结果：")
    for title, passed in results:
        print(f"  {'通过' if passed else '失败'}  {title}")
    if not args.postgres:
        print("  未运行  PostgreSQL 测试（生产使用 PostgreSQL 时，发布前必须加 --postgres 运行）")
    sys.exit(0 if all(passed for _, passed in results) else 1)


if __name__ == "__main__":
    main()
