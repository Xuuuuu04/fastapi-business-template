"""
离线面板数据按项目图组织，节点只含声明与摘要，禁止导出完整测试运行数据。
"""

from datetime import UTC, datetime
from pathlib import Path

from fastapi_project.development.history import read_checks
from fastapi_project.development.panel_dependencies import dependency_issues
from fastapi_project.development.panel_duplicates import duplicate_hints
from fastapi_project.development.panel_evidence import node_evidence
from fastapi_project.development.panel_git import branch_status
from fastapi_project.development.panel_records import recent_records
from fastapi_project.development.panel_sources import attention, metrics, package_note, package_size
from fastapi_project.development.status import project_status

from shared.modules.catalog import Catalog


# 操作详情只列位置和实现身份；最近运行的输入、SQL、结果和外部回执不进面板。
def module_detail(module: dict) -> dict:
    return {
        "name": module["name"],
        "title": module["title"],
        "kind": module["kind"],
        "code": module["code"],
        "enabled": module["enabled"],
        "operations": [
            {
                "name": operation["name"],
                "title": operation["title"],
                "implementation": operation["implementation"],
                "steps": [
                    {key: step[key] for key in ("name", "title", "source", "simulated")}
                    for step in operation["steps"]
                ],
            }
            for operation in module["operations"]
        ],
        "rules": [
            {key: rule[key] for key in ("id", "risk", "state", "revision")}
            for rule in module["rule_ledger"]
        ],
        "tests": {
            database: {
                key: suite[key] for key in ("finished_at", "current", "checks_passed", "counts")
            }
            for database, suite in module["tests"]["latest"].items()
        },
    }


# 已登记但未写入计划的包也明确列出，工具包单独展示真实使用者。
def nodes(project: Path, status: dict, checks: list[dict]) -> list[dict]:
    planned = {
        package["module"]: (line["name"], package)
        for line in status["lines"]
        for package in line["packages"]
    }
    libraries = {library["name"]: library for library in status["libraries"]}
    result = []
    for name in dict.fromkeys([*planned, *status["modules"], *libraries]):
        line, package = planned.get(name, ("计划外", {"title": name, "operations": []}))
        module = status["modules"].get(name)
        detail = module_detail(module) if module else {"operations": [], "rules": []}
        evidence = node_evidence(name, status, checks)
        if name in libraries:
            detail = {**libraries[name], "operations": [], "rules": []}
            evidence = {
                "state": "unknown",
                "reason": "工具源码已登记，尚无独立整链稳定证据",
                "flaky": False,
                "checks": [],
            }
        size = package_size(
            project,
            name,
            module or {"kind": "library" if name in libraries else "unknown"},
            status["dependencies"],
        )
        result.append(
            {
                "id": name,
                "title": module["title"] if module else package["title"],
                "line": line,
                "kind": module["kind"]
                if module
                else package.get("kind", "library" if name in libraries else "unknown"),
                "planned_operations": package["operations"],
                "size": size,
                "pending_confirmation": any(
                    rule["risk"] == "high" and rule["state"] not in {"confirmed", "retired"}
                    for rule in detail["rules"]
                ),
                **detail,
                **evidence,
            }
        )
    return result


# 实线来自当前声明，虚线仅来自计划；已登记只读例外另色并展示调用数量。
def edges(catalog: Catalog, status: dict) -> list[dict]:
    result = []
    actual = status["dependencies"]
    for source, targets in actual.items():
        for target, titles in targets.items():
            module = catalog.modules[source]
            exception = module.kind == "capability" and target in module.read_dependencies
            result.append(
                {
                    "source": source,
                    "target": target,
                    "kind": "exception" if exception else "actual",
                    "count": len(titles),
                }
            )
    for line in status["lines"]:
        for package in line["packages"]:
            for target in package.get("dependencies", []):
                if target not in actual.get(package["module"], {}):
                    result.append(
                        {
                            "source": package["module"],
                            "target": target,
                            "kind": "planned",
                            "count": 1,
                        }
                    )
    for source, targets in status["library_dependencies"].items():
        for target in targets:
            result.append({"source": source, "target": target, "kind": "library", "count": 1})
    return result


# 单一数据入口不访问业务服务；错误由命令明确报出而不是用空图冒充正常。
def panel_data(project: Path, catalog: Catalog) -> dict:
    status = project_status(catalog, project)
    checks = read_checks(project, include_cases=False)
    graph = nodes(project, status, checks)
    duplicates = duplicate_hints(project)
    issues, invalid_edges = dependency_issues(project)
    for node in graph:
        node["note"] = package_note(project, node["id"])
        node["recent_records"] = recent_records(node["id"], status, checks)
        node["duplicates"] = [
            hint
            for hint in duplicates
            if any(location["package"] == node["id"] for location in hint["locations"])
        ]
        node["size"]["suggest_split"] |= bool(node["duplicates"])
    return {
        "schema_version": 1,
        "name": status["name"],
        "generated_at": datetime.now(UTC).isoformat(),
        "meaning": "绿色表示当前代码及整链稳定检查通过，不代表业务验收；规则确认独立显示。",
        "nodes": graph,
        "edges": edges(catalog, status) + invalid_edges,
        "tasks": status["tasks"],
        "attention": attention(project),
        "git": branch_status(project),
        "metrics": metrics(checks, project),
        "duplicates": duplicates,
        "dependency_issues": issues,
        "lines": [
            {"name": line["name"], "packages": [package["module"] for package in line["packages"]]}
            for line in status["lines"]
        ],
    }
