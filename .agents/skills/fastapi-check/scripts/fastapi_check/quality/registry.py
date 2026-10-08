"""
检查登记是否完整：service/ 下每个模块都在总目录登记；对外开放的操作接到了接口或后台任务上；
只供内部调用的操作确实被某个步骤调用。只凭登记表判断“已接好”是不够的，这里对照真实的接口文件。
“每个操作都被测试执行过”由 tests/conftest.py 在完整运行默认测试时检查。
"""

from pathlib import Path

from fastapi_check.quality.report import Problem
from fastapi_check.quality.rules import ROOT

from shared.modules.catalog import Catalog


# 检查模块登记和连接情况。
def check_registry(catalog: Catalog, root: Path = ROOT) -> list[Problem]:
    problems = check_listed(catalog, root)
    routes = text_of(root / "app" / "api")
    used = {
        used
        for binding in catalog.bindings.values()
        for part in binding.flow.steps
        for used in part.uses
    }
    for item in catalog.bindings:
        where = f"service/{item.module}/public.py"
        if (
            item.entry
            and f".{item.action}" not in routes
            and catalog.plan(item.name) is None
            and catalog.identity is not item
        ):
            problems.append(
                Problem(
                    where,
                    0,
                    "not_exposed",
                    f"操作 {item.name} 对外开放，但没有接口或后台任务使用它",
                    "在 app/api/v1 中加接口，或改成 entry=False",
                )
            )
        if not item.entry and item not in used:
            problems.append(Problem(where, 0, "unused", f"内部操作 {item.name} 没有被任何步骤调用"))
    return problems


# 检查 service/ 下的模块目录与总目录一致。
def check_listed(catalog: Catalog, root: Path) -> list[Problem]:
    found = {path.parent.name for path in (root / "service").glob("*/module.py")}
    problems = [
        Problem(
            f"service/{name}", 0, "not_listed", f"模块 {name} 没有在 app/setup/catalog.py 中登记"
        )
        for name in sorted(found - set(catalog.modules))
    ]
    problems += [
        Problem(
            "app/setup/catalog.py", 0, "missing_module", f"登记的模块 {name} 在 service/ 下找不到"
        )
        for name in sorted(set(catalog.modules) - found)
    ]
    return problems


# 读取目录下全部 Python 文件的文本。
def text_of(folder: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in folder.rglob("*.py"))
