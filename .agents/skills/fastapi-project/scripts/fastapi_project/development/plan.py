import json
import re
from pathlib import Path
from typing import Any

NAME = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$")
OPERATION = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")


def read_plan(project: Path) -> dict[str, Any] | None:
    path = project / "project-plan.json"
    if not path.exists():
        return None
    plan = json.loads(path.read_text(encoding="utf-8"))
    check_plan(plan)
    return plan


def check_plan(plan: Any) -> None:
    if not isinstance(plan, dict) or plan.get("schema_version") not in {1, 2}:
        raise ValueError("project-plan.json 的 schema_version 必须为 1或2")
    if not isinstance(plan.get("name"), str) or not plan["name"].strip():
        raise ValueError("项目名称不能为空")
    lines = plan.get("lines")
    if not isinstance(lines, list):
        raise ValueError("lines 必须为业务线列表")
    seen: set[str] = set()
    titles: set[str] = set()
    for line in lines:
        if not isinstance(line, dict) or not isinstance(line.get("name"), str):
            raise ValueError("业务线必须有名称")
        if not line["name"].strip() or line["name"] in titles:
            raise ValueError("业务线名称不能为空或重复")
        titles.add(line["name"])
        if not isinstance(line.get("packages"), list):
            raise ValueError("packages 必须为开发包列表")
        for package in line["packages"]:
            check_package(package, seen, allow_empty=plan["schema_version"] == 2)
    check_dependencies(lines)


def check_dependencies(lines: list[dict[str, Any]]) -> None:
    packages = [package for line in lines for package in line["packages"]]
    edges = {package["module"]: package.get("dependencies", []) for package in packages}
    for name, dependencies in edges.items():
        missing = sorted(set(dependencies) - set(edges))
        if name in dependencies:
            missing.append(name)
        if missing:
            raise ValueError(f"开发包 {name} 依赖了计划外的模块：{missing}")
    for start in edges:
        seen = set()
        pending = list(edges[start])
        while pending:
            current = pending.pop()
            if current == start:
                raise ValueError(f"开发包依赖出现循环：{start}")
            if current not in seen:
                seen.add(current)
                pending.extend(edges.get(current, []))


def check_package(package: Any, seen: set[str], *, allow_empty: bool = False) -> None:
    if not isinstance(package, dict):
        raise ValueError("开发包必须为对象")
    name = package.get("module")
    if not isinstance(name, str) or not NAME.fullmatch(name) or name in seen:
        raise ValueError(f"模块名无效或重复：{name}")
    seen.add(name)
    if not isinstance(package.get("title"), str) or not package["title"].strip():
        raise ValueError(f"开发包 {name} 的名称不能为空")
    operations = package.get("operations")
    if not isinstance(operations, list) or (not operations and not allow_empty):
        raise ValueError(f"开发包 {name} 必须列出预期操作")
    if any(not isinstance(item, str) or not OPERATION.fullmatch(item) for item in operations):
        raise ValueError(f"开发包 {name} 的操作名只能用小写字母、数字和下划线")
    check_implemented(package)
    if len(set(operations)) != len(operations):
        raise ValueError(f"开发包 {name} 的操作重复")
    if package.get("kind", "capability") not in {"capability", "workflow", "library"}:
        raise ValueError(f"开发包 {name} 的kind无效")
    dependencies = package.get("dependencies", [])
    if not isinstance(dependencies, list) or any(
        not isinstance(item, str) or not NAME.fullmatch(item) for item in dependencies
    ):
        raise ValueError(f"开发包 {name} 的dependencies无效")


def check_implemented(package: dict) -> None:
    values = package.get("implemented_operations", [])
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise ValueError("implemented_operations必须是操作名列表")
    extra = set(values) - set(package["operations"])
    if extra:
        raise ValueError(
            f"开发包{package['module']}请同步移除或改名implemented_operations中的{sorted(extra)}"
        )
