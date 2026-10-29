import ast
import importlib
from pathlib import Path
from typing import Any

from shared.flow.step import source_of


def local_routes() -> dict[str, list[dict[str, Any]]]:
    path = Path(__file__).resolve().parents[6] / "server/app/api/routers.py"
    tree = ast.parse(path.read_text())
    imports = {
        alias.asname or alias.name: (node.module, alias.name)
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    declaration = next(
        (
            node.value
            for node in tree.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "MODULE_ROUTERS"
        ),
        None,
    )
    if isinstance(declaration, ast.Dict) and not declaration.values:
        return {}
    routers = registered_routers(declaration, imports)
    if routers is None:
        from app.api.routers import MODULE_ROUTERS

        routers = [r for group in MODULE_ROUTERS.values() for r in group]
    from fastapi import FastAPI

    app = FastAPI()
    for router in routers:
        app.include_router(router)
    return route_details(app)


def registered_routers(declaration: ast.expr | None, imports: dict) -> list[Any] | None:
    if not isinstance(declaration, ast.Dict):
        return None
    result = []
    for group in declaration.values:
        if not isinstance(group, (ast.Tuple, ast.List)):
            return None
        for router in group.elts:
            if not isinstance(router, ast.Attribute) or not isinstance(router.value, ast.Name):
                return None
            imported = imports.get(router.value.id)
            if not imported or imported[0] is None:
                return None
            module, name = imported
            owner = importlib.import_module(f"{module}.{name}")
            result.append(getattr(owner, router.attr))
    return result


def route_details(app: Any) -> dict[str, list[dict[str, Any]]]:
    from fastapi.routing import APIRoute, iter_route_contexts
    from fastapi_docs.flow_doc import contracts_used

    found: dict[str, list[dict[str, Any]]] = {}
    for route in iter_route_contexts(app.routes):
        if not isinstance(route.route, APIRoute) or route.endpoint is None:
            continue
        for name in contracts_used(route.endpoint):
            found.setdefault(name, []).append(
                {
                    "path": route.path,
                    "methods": sorted(route.methods or ()),
                    "source": "server/" + source_of(route.endpoint),
                }
            )
    return found
