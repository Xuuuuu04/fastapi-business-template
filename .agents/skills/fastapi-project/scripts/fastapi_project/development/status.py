"""
把预先设计、实际声明与检查记录对应起来。
完成比例的单位是计划中的公开操作；没有设计时不计算比例。
"""

from pathlib import Path
from typing import Any

from fastapi_docs.progress_doc import pending_of, rules_of, tested_rules
from fastapi_project.development.check_storage import load_cases
from fastapi_project.development.evidence import (
    case_current,
    check_scope,
    full_check_current,
    latest_full_check,
)
from fastapi_project.development.history import fingerprints, module_checks, read_checks
from fastapi_project.development.ledger import read_ledger
from fastapi_project.development.operations import operation_status
from fastapi_project.development.pipelines import overview
from fastapi_project.development.plan import read_plan
from fastapi_project.development.scenarios import scenario_status
from fastapi_project.development.task_views import task_status

from shared.graphs.static import module_graph
from shared.modules.catalog import Catalog
from shared.modules.libraries import library_links, library_specs


# 筛出属于本模块的测试，也保留其他模块测试中实际调用本模块的记录。
def relevant_cases(suite: dict[str, Any], module: str) -> list[dict[str, Any]]:
    prefixes = (f"tests/modules/{module}/", f"tests/integration/{module}/")
    return [
        case
        for case in suite["cases"]
        if case["nodeid"].startswith(prefixes)
        or any(identity.startswith(module + ".") for identity in case.get("scenario_ids", []))
        or any(run["operation"].startswith(module + ".") for run in case["runs"])
    ]


# 返回本模块最近的各数据库测试与适用于当前代码的测试记录。
def test_status(
    checks: list[dict[str, Any]],
    name: str,
    fingerprint: str,
    versions: dict[str, str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    formal = [check for check in checks if check_scope(check)["kind"] != "quick"]
    result = module_checks(formal, name, fingerprint)
    current: list[dict[str, Any]] = []
    for suite in result["latest"].values():
        cases = [
            {**case, "current": case_current(case, suite, versions or {name: fingerprint})}
            for case in relevant_cases(suite, name)
        ]
        suite["counts"] = {
            status: sum(case["outcome"] == status for case in cases)
            for status in ("passed", "failed", "skipped")
        }
        suite["cases"] = cases
        if suite["current"]:
            current += [case for case in cases if case["current"]]
    return result, current


# 一个模块的结构、规则、最近检查和运行证据。
def module_status(
    catalog: Catalog,
    project: Path,
    name: str,
    checks: list[dict[str, Any]],
    fingerprint: str,
    disabled: set[str],
    versions: dict[str, str],
) -> dict[str, Any]:
    module = catalog.modules[name]
    tests, current = test_status(checks, name, fingerprint, versions)
    rules = rules_of(project / module.doc / "rules.md")
    return {
        "name": name,
        "title": module.title,
        "kind": module.kind or "unknown",
        "enabled": name not in disabled,
        "code": f"server/service/{name}",
        "fingerprint": fingerprint,
        "rules": rules,
        "rule_ledger": [
            r.model_dump(mode="json")
            for r in read_ledger(project).rules
            if r.id.startswith(name + ".")
        ],
        "test_annotations": tested_rules(project, name),
        "pending": [item.text for item in pending_of(project, name)],
        "tests": tests,
        "scenarios": scenario_status(project, name, tests),
        "operations": [operation_status(catalog, item.name, current) for item in module.provides],
    }


# 比较一个计划开发包；登记完整只证明静态结构存在。
def package_status(package: dict[str, Any], modules: dict[str, Any]) -> dict[str, Any]:
    module = modules.get(package["module"])
    planned = [f"{package['module']}.{name}" for name in package["operations"]]
    actual = {item["name"]: item for item in module["operations"]} if module else {}
    implemented = [name for name in planned if name in actual]
    successful = [name for name in implemented if actual[name]["test_executions"].get("ok", 0)]
    return {
        **package,
        "planned": planned,
        "registered": implemented,
        "missing": sorted(set(planned) - actual.keys()),
        "extra": sorted(actual.keys() - set(planned)),
        "test_successful": successful,
        "enabled": module["enabled"] if module else False,
    }


# 全局失败包含框架与质量测试，不仅是业务模块中的测试。
def latest_check_status(check: dict[str, Any]) -> dict[str, Any]:
    from fastapi_project.development.summary import test_summary

    suites = {}
    for suite in check["suites"]:
        cases = load_cases(suite)
        suites[suite["database"]] = {
            **suite,
            "cases": cases,
            "finished_at": check["finished_at"],
            "current": not check["source_changed"],
            "checks_passed": check["passed"],
            "counts": {
                status: sum(case["outcome"] == status for case in cases)
                for status in ("passed", "failed", "skipped")
            },
        }
    result = {key: check[key] for key in ("finished_at", "checks", "passed", "source_changed")}
    result["recorded_modules"] = sorted(check["fingerprints"])
    result["scope"] = check_scope(check)
    result["timings"] = check.get("timings")
    result["elapsed_seconds"] = check.get("elapsed_seconds")
    result["suites"] = test_summary({"rounds": 1, "latest": suites})["latest"]
    # 全局摘要仅知道该轮运行期间是否改过源码；当前适用性由各模块的版本判断。
    for suite in result["suites"].values():
        del suite["current"]
    return result


# 完整检查独立保留，之后的局部成功不能遮住框架失败。
def full_check_status(
    checks: list[dict[str, Any]], versions: dict[str, str], project: Path | None = None
) -> dict[str, Any] | None:
    check = latest_full_check(checks)
    return (
        {**latest_check_status(check), "current": full_check_current(check, versions, project)}
        if check
        else None
    )


# 从项目根开始汇总；计划外模块另外列出，避免它们被遗漏。
def project_status(
    catalog: Catalog,
    project: Path,
    disabled: set[str] | None = None,
    extra_checks: list[Path] | None = None,
) -> dict[str, Any]:
    plan = read_plan(project)
    checks = read_checks(project, extra_checks, include_cases=False)
    codes = fingerprints(project, list(catalog.modules), catalog.links())
    modules = {
        name: module_status(catalog, project, name, checks, codes[name], disabled or set(), codes)
        for name in catalog.modules
    }
    lines = plan_lines(plan, modules)
    packages = [package for line in lines for package in line["packages"]]
    expected = {package["module"] for package in packages}
    totals = {
        key: sum(len(package[key]) for package in packages)
        for key in ("planned", "registered", "test_successful")
    }
    denominator = totals["planned"]
    ratios = (
        {key: round(totals[key] / denominator, 4) for key in ("registered", "test_successful")}
        if denominator
        else None
    )
    return {
        "schema_version": 1,
        "tasks": task_status(project, catalog),
        "name": plan["name"] if plan else project.name,
        "has_plan": plan is not None,
        "lines": lines,
        "totals": totals if denominator else None,
        "ratios": ratios,
        "unplanned_modules": sorted(modules.keys() - expected),
        "modules": modules,
        "module_graph": module_graph(catalog),
        "dependencies": catalog.links(),
        "libraries": [item.shape() for item in library_specs(project / "server")],
        "library_dependencies": library_links(project / "server"),
        "check_rounds": len(checks),
        "latest_check": latest_check_status(checks[-1]) if checks else None,
        "latest_full_check": full_check_status(checks, codes, project),
        "runtime": None,
        "pipelines": overview(catalog, project),
    }


# 业务线按设计保留顺序，未实现的开发包也参加比较。
def plan_lines(plan: dict[str, Any] | None, modules: dict[str, Any]) -> list[dict[str, Any]]:
    if plan is None:
        return []
    return [
        {
            "name": line["name"],
            "packages": [package_status(package, modules) for package in line["packages"]],
        }
        for line in plan["lines"]
    ]


# 计划中尚未开发的操作也参加比较；无数据库证据或没有计划时比例保持未知。
def runtime_progress(status: dict[str, Any], disabled: set[str], module: str = "") -> None:
    runtime = status["runtime"]
    planned = {
        name
        for line in status["lines"]
        for package in line["packages"]
        for name in package["planned"]
        if package["module"] not in disabled and (not module or package["module"] == module)
    }
    seen = planned.intersection(runtime["current_successful"])
    runtime["planned_successful"] = sorted(seen)
    runtime["sample_ratio"] = len(seen) / len(planned) if planned and runtime["available"] else None
