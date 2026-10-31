from pathlib import Path

from fastapi_business.routes import local_routes
from fastapi_check.quality.report import Problem
from fastapi_check.quality.rules import ROOT

from shared.modules.catalog import Catalog


def check_registry(catalog: Catalog, root: Path = ROOT) -> list[Problem]:
    problems = check_listed(catalog, root)
    routes = local_routes(root)
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
            and item.name not in routes
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
