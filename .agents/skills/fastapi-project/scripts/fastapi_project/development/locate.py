import ast
import inspect
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from shared.data.fields import nested_models, notes_of
from shared.modules.catalog import Binding, Catalog
from shared.pipelines.plan import stages_of

DETAIL_LIMIT = 12
COMMAND = "uv run dev "


def declaration_source(project: Path, module: str) -> str:
    path = project / "server/service" / module / "module.py"
    if not path.is_file():
        return "未知"
    for node in ast.walk(ast.parse(path.read_text())):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Module"
        ):
            return f"server/service/{module}/module.py:{node.lineno}"
    return "未知"


def model_source(model: type, project: Path) -> str:
    try:
        path = Path(inspect.getfile(model)).resolve()
        line = inspect.getsourcelines(model)[1]
        return f"{path.relative_to(project)}:{line}"
    except (OSError, TypeError, ValueError):
        return "未知"


def field_terms(model: type[BaseModel], seen: set[type] | None = None) -> list[str]:
    seen = seen if seen is not None else set()
    if model in seen:
        return []
    seen.add(model)
    terms = [f"{name} {note.meaning}" for name, note in notes_of(model).items()]
    for field in model.model_fields.values():
        for inner in nested_models(field.annotation):
            terms.extend(field_terms(inner, seen))
    return terms


def operation_terms(binding: Binding, routes: list[dict]) -> list[str]:
    module, item, flow = binding.module, binding.contract, binding.flow
    terms = [module.name, module.title, *module.aliases, item.name, item.title, *item.aliases]
    terms += [
        flow.title,
        *field_terms(flow.work),
        *field_terms(item.input),
        *field_terms(item.output),
    ]
    terms += [table.name for table in module.tables]
    for part in flow.steps:
        terms += [part.title]
    terms += [route["path"] for route in routes]
    terms += [s.name + " " + s.title for s in module.schedules if s.contract is item]
    terms += [j.contract.name + " " + j.contract.title for j in module.jobs if j.contract is item]
    terms += [
        p.name + " " + p.title
        for p in module.pipelines
        if p.start is item or any(s.operation is item for s in stages_of(p))
    ]
    return terms


def bounded(values: list) -> dict[str, Any]:
    return {"items": values[:DETAIL_LIMIT], "omitted": max(0, len(values) - DETAIL_LIMIT)}


def result_of(binding: Binding, project: Path, routes: list[dict]) -> dict[str, Any]:
    module, item = binding.module, binding.contract
    steps = [
        {"name": p.name, "title": p.title, "source": f"server/{p.source}"}
        for p in binding.flow.steps
    ]
    files = [
        declaration_source(project, module.name),
        model_source(item.input, project),
        model_source(item.output, project),
        model_source(binding.flow.work, project),
        *[s["source"] for s in steps],
    ]
    return {
        "module": module.name,
        "module_title": module.title,
        "module_aliases": list(module.aliases),
        "operation": item.name,
        "title": item.title,
        "aliases": list(item.aliases),
        "files": bounded(list(dict.fromkeys(files))),
        "steps": bounded(steps),
        "interfaces": bounded(routes),
        "schedules": bounded([s.name for s in module.schedules if s.contract is item]),
        "pipelines": bounded(
            [
                p.name
                for p in module.pipelines
                if p.start is item or any(s.operation is item for s in stages_of(p))
            ]
        ),
        "tables": bounded([t.name for t in module.tables]),
        "table_relation": "模块归属；具体步骤实际访问未知",
        "next": COMMAND + f"check --module {module.name}",
    }


def locate(
    catalog: Catalog,
    project: Path,
    query: str,
    limit: int = 10,
    routes: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    query = query.strip().casefold()
    if not query or not 1 <= limit <= 100:
        raise ValueError("query 不能为空，limit 必须在 1 到 100 之间")
    routes = routes or {}
    matches = []
    for binding in catalog.bindings.values():
        terms = operation_terms(binding, routes.get(binding.contract.name, []))
        folded = [term.casefold() for term in terms if term]
        if any(query in term for term in folded):
            matches.append((query not in folded, binding.contract.name, binding))
    matches.sort(key=lambda match: match[:2])
    results = [
        result_of(b, project, routes.get(b.contract.name, [])) for _, _, b in matches[:limit]
    ]
    for result, (_, _, binding) in zip(results, matches[:limit], strict=True):
        terms = operation_terms(binding, routes.get(binding.contract.name, []))
        result["matched"] = bounded(list(dict.fromkeys(t for t in terms if query in t.casefold())))
    return {
        "query": query,
        "limit": limit,
        "total": len(matches),
        "omitted": max(0, len(matches) - limit),
        "results": results,
        "database_read": False,
        "runtime": "未知",
        "unregistered_route_operations": bounded(sorted(set(routes) - set(catalog.by_name))),
    }
