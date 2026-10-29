from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Request

from app.api.identity import CallerDep, require
from shared.errors.kinds import BusinessError, Kind
from shared.graphs.lineage import explain, field_sources, lineage_graph
from shared.graphs.static import flow_graph, module_graph
from shared.modules.catalog import Binding, Catalog

router = APIRouter(prefix="/api/system", tags=["运行排查"])

PERMISSION = "system.diagnostics"


class NotRegistered(BusinessError):
    code = "not_registered"
    kind = Kind.NOT_FOUND
    message = "没有登记这个操作或字段"


@router.get("/modules", summary="模块目录和关系图", operation_id="system_modules")
async def modules(request: Request, caller: CallerDep) -> dict[str, Any]:
    require(caller, PERMISSION)
    catalog: Catalog = request.app.state.services.catalog
    items = []
    for module in catalog.modules.values():
        operations = [
            {"name": item.name, "title": item.title, "access": item.access, "entry": item.entry}
            for item in module.provides
        ]
        items.append(
            {
                "name": module.name,
                "title": module.title,
                "version": module.version,
                "operations": operations,
                "identity": module.identity.name if module.identity is not None else None,
                "identity_header": module.identity_header,
                "identity_token": module.identity_token,
                "schedules": [
                    {
                        "name": plan.name,
                        "org_ids": plan.org_ids,
                        "slot_input_field": plan.slot_input_field,
                    }
                    for plan in module.schedules
                ],
            }
        )
    return {
        "digest": catalog.digest,
        "modules": items,
        "links": catalog.links(),
        "graph": module_graph(catalog),
    }


@router.get("/flows/{name}", summary="操作的计算流程", operation_id="system_flow")
async def flow(name: str, request: Request, caller: CallerDep) -> dict[str, Any]:
    require(caller, PERMISSION)
    binding = find(request, name)
    fields = [asdict(source) for source in field_sources(binding).values()]
    return {
        "name": name,
        "title": binding.contract.title,
        "module": binding.module.name,
        "graph": flow_graph(binding),
        "fields": fields,
        "steps": [
            {
                "name": part.name,
                "title": part.title,
                "kind": part.kind,
                "source": part.source,
                "reads": part.reads,
                "writes": part.writes,
                "condition": part.when.title if part.when else "",
                "calls": [{"name": item.name, "title": item.title} for item in part.uses],
                "jobs": [{"name": item.name, "title": item.title} for item in part.later],
            }
            for part in binding.flow.steps
        ],
    }


@router.get("/fields/{name}/{field}", summary="字段来源", operation_id="system_field")
async def field(name: str, field: str, request: Request, caller: CallerDep) -> dict[str, Any]:
    require(caller, PERMISSION)
    binding = find(request, name)
    if field not in binding.types.notes:
        raise NotRegistered(f"流程“{binding.flow.title}”中没有字段 {field}")
    return {
        "name": name,
        "field": field,
        "explain": explain(binding, field),
        "graph": lineage_graph(binding, field),
    }


def find(request: Request, name: str) -> Binding:
    binding = request.app.state.services.catalog.find(name)
    if binding is None:
        raise NotRegistered(f"没有登记操作 {name}")
    return binding
