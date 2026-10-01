"""
结构查询：模块关系图、操作的计算流程图、字段来源。内容来自模块声明，不涉及业务数据。
需要权限 system.diagnostics。
"""

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Request

from app.api.identity import CallerDep, require
from shared.errors.kinds import BusinessError, Kind
from shared.graphs.lineage import explain, field_sources, lineage_graph
from shared.graphs.static import flow_graph, module_graph
from shared.modules.catalog import Binding, Catalog

router = APIRouter(prefix="/api/system", tags=["运行诊断"])

PERMISSION = "system.diagnostics"


class NotRegistered(BusinessError):
    code = "not_registered"
    kind = Kind.NOT_FOUND
    message = "没有登记这个操作或字段"


# 列出全部模块、操作和模块关系图。
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
                "doc": module.doc,
                "operations": operations,
            }
        )
    return {
        "digest": catalog.digest,
        "modules": items,
        "links": catalog.links(),
        "graph": module_graph(catalog),
    }


# 返回一个操作的计算流程图和全部字段的来源。
@router.get("/flows/{name}", summary="操作的计算流程", operation_id="system_flow")
async def flow(name: str, request: Request, caller: CallerDep) -> dict[str, Any]:
    require(caller, PERMISSION)
    binding = find(request, name)
    fields = [asdict(source) for source in field_sources(binding).values()]
    return {
        "name": name,
        "title": binding.contract.title,
        "module": binding.module.name,
        "doc": binding.module.doc,
        "graph": flow_graph(binding),
        "fields": fields,
        "steps": [
            {
                "name": part.name,
                "title": part.title,
                "kind": part.kind,
                "rule": part.rule,
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


# 逐层说明一个字段的来源，并给出来源图。
@router.get("/fields/{name}/{field}", summary="字段来源", operation_id="system_field")
async def field(name: str, field: str, request: Request, caller: CallerDep) -> dict[str, Any]:
    require(caller, PERMISSION)
    binding = find(request, name)
    if field not in binding.types.notes:
        raise NotRegistered(f"流程「{binding.flow.title}」中没有字段 {field}")
    return {
        "name": name,
        "field": field,
        "explain": explain(binding, field),
        "graph": lineage_graph(binding, field),
    }


# 按操作名查找登记的实现。
def find(request: Request, name: str) -> Binding:
    binding = request.app.state.services.catalog.find(name)
    if binding is None:
        raise NotRegistered(f"没有登记操作 {name}")
    return binding
