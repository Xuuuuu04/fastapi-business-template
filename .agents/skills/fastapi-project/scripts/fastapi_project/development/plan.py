"""
读取项目的预先设计：业务线、开发包与预期操作。
计划不登记代码、不生成业务规则；未实现的模块和操作可以先写进来。
"""

import json
import re
from pathlib import Path
from typing import Any

NAME = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$")
OPERATION = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")


# 读取计划；缺少计划时保留未知，不从当前实现猜出总目标。
def read_plan(project: Path) -> dict[str, Any] | None:
    path = project / "project-plan.json"
    if not path.exists():
        return None
    plan = json.loads(path.read_text(encoding="utf-8"))
    check_plan(plan)
    return plan


# 验证设计图，避免重复开发包和空操作让完成比例失去意义。
def check_plan(plan: Any) -> None:
    if not isinstance(plan, dict) or plan.get("schema_version") != 1:
        raise ValueError("project-plan.json 的 schema_version 必须为 1")
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
            check_package(package, seen)


# 一个模块只属于一个开发包，公开操作按本模块内的名称列出。
def check_package(package: Any, seen: set[str]) -> None:
    if not isinstance(package, dict):
        raise ValueError("开发包必须为对象")
    name = package.get("module")
    if not isinstance(name, str) or not NAME.fullmatch(name) or name in seen:
        raise ValueError(f"模块名无效或重复：{name}")
    seen.add(name)
    if not isinstance(package.get("title"), str) or not package["title"].strip():
        raise ValueError(f"开发包 {name} 的名称不能为空")
    operations = package.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ValueError(f"开发包 {name} 必须列出预期操作")
    if any(not isinstance(item, str) or not OPERATION.fullmatch(item) for item in operations):
        raise ValueError(f"开发包 {name} 的操作名只能用小写字母、数字和下划线")
    if len(set(operations)) != len(operations):
        raise ValueError(f"开发包 {name} 的操作重复")
