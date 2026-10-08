"""
计划操作的一致性：未实现计划可保留，已实现名称必须与当前登记对应，错误指出准确JSON位置。
"""

import json
import re
from pathlib import Path
from typing import Any

from shared.modules.catalog import Catalog

HEADING = re.compile(r"^## .+（([a-z0-9_.]+)）$", re.MULTILINE)


# 旧提交的flows文档和显式implemented_operations都是已实现证据，不猜业务名字。
def observed(project: Path, module: str) -> set[str]:
    path = project / "doc" / module / "flows.md"
    try:
        text = path.read_text()
    except OSError:
        return set()
    return {
        name.partition(".")[2] for name in HEADING.findall(text) if name.startswith(module + ".")
    }


# 计划错误直接说明要改哪一项，普通planned名称不因尚未登记而失败。
def check_entries(catalog: Catalog, project: Path, plan: dict[str, Any] | None) -> list[str]:
    if plan is None:
        return []
    problems = []
    for line_index, line in enumerate(plan["lines"]):
        for package_index, package in enumerate(line["packages"]):
            name = package["module"]
            actual = {
                item.contract.name.partition(".")[2]
                for item in catalog.by_name.values()
                if item.contract.module == name
            }
            known = set(package.get("implemented_operations", [])) | observed(project, name)
            for operation_index, operation in enumerate(package["operations"]):
                if operation in known and operation not in actual:
                    where = (
                        f"project-plan.json $.lines[{line_index}].packages[{package_index}]"
                        f".operations[{operation_index}]"
                    )
                    problems.append(
                        f"{where}：已实现操作{name}.{operation}已删除或改名，请更新该项；当前登记{sorted(actual)}"
                    )
    return problems


# 导出时记录实际对应过的操作，后续删除flows也仍能查到旧计划项。
def capture(catalog: Catalog, project: Path, plan: dict[str, Any] | None) -> bool:
    if plan is None:
        return False
    changed = False
    for line in plan["lines"]:
        for package in line["packages"]:
            declared = set(package["operations"])
            known = set(package.get("implemented_operations", []))
            actual = {
                item.contract.name.partition(".")[2]
                for item in catalog.by_name.values()
                if item.contract.module == package["module"]
            }
            updated = sorted(declared & (known | actual | observed(project, package["module"])))
            if updated != package.get("implemented_operations", []):
                package["implemented_operations"] = updated
                changed = True
    if changed:
        (project / "project-plan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
        )
    return changed
