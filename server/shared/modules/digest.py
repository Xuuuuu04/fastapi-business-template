"""
模块声明摘要包含操作、任务参数、定时参数与身份入口，避免接口和worker拿着不同计划运行。
只序列化声明信息，身份令牌等秘密字段由数据模型脱敏。
"""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

from shared.db.budget import DEFAULT_BUDGET
from shared.jobs.plan import JobPlan
from shared.modules.module import Module
from shared.pipelines.plan import FanOut, Stage


# 稳定序列化同一份声明，任务与计划参数变化会改变摘要。
def digest_of(modules: Sequence[Module]) -> str:
    shape = [module_shape(module) for module in sorted(modules, key=lambda item: item.name)]
    text = json.dumps(shape, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


# 每个模块记录流程、后台任务、时段与组织选择；不会调用业务代码。
def module_shape(module: Module) -> dict[str, Any]:
    return {
        "name": module.name,
        "version": module.version,
        **({"aliases": module.aliases} if module.aliases else {}),
        **(
            {"operation_aliases": {c.name: c.aliases for c in module.provides if c.aliases}}
            if any(c.aliases for c in module.provides)
            else {}
        ),
        **table_shape(module),
        "flows": {
            item.name: [[part.name, part.reads, part.writes, part.saves] for part in flow.steps]
            for item, flow in sorted(module.provides.items(), key=lambda pair: pair[0].name)
        },
        **endpoint_shapes(module),
        "query_budgets": query_budgets(module),
        "jobs": [job_shape(j) for j in sorted(module.jobs, key=lambda item: item.contract.name)],
        "schedules": [
            dict(
                name=s.name,
                contract=s.contract.name,
                input=s.input.model_dump(mode="json"),
                every=s.every.total_seconds() if s.every else None,
                daily_at=s.daily_at.isoformat() if s.daily_at else None,
                zone=s.zone,
                missed=s.missed,
                grace=s.grace.total_seconds(),
                slot_input_field=s.slot_input_field,
                org_ids=s.org_ids,
            )
            for s in sorted(module.schedules, key=lambda item: item.name)
        ],
        "pipelines": pipeline_shapes(module),
        "identity": module.identity.name if module.identity is not None else None,
        "identity_header": module.identity_header,
        "identity_token": module.identity_token,
    }


# 后台任务的恢复、安全和导入预期共同决定声明版本。
def job_shape(plan: JobPlan) -> dict[str, Any]:
    return dict(
        contract=plan.contract.name,
        retries=plan.retry.times,
        waits=plan.retry.waits,
        repeat_safe=plan.repeat_safe,
        max_queued=plan.max_queued,
        lease_seconds=plan.lease_seconds,
        critical=plan.critical,
        import_plan=plan.import_plan.shape() if plan.import_plan else None,
        segmented=plan.segmented,
        cursor=plan.cursor.model_json_schema() if plan.cursor else None,
    )


# 表归属与现行表共用声明摘要，历史维护权限改变后旧检查过期。
def table_shape(module: Module) -> dict[str, Any]:
    return {
        "tables": [table.key for table in module.tables],
        "owned_tables": module.owned_tables,
        "external_tables": module.external_tables,
    }


# 流程声明影响同一登记摘要，内部实现不在本摘要中。
def pipeline_shapes(module: Module) -> list[dict[str, Any]]:
    return [
        dict(
            name=p.name,
            overlap=p.overlap,
            input=p.input.model_json_schema(),
            complete_by=(
                dict(
                    at=p.complete_by.at.isoformat(),
                    zone=p.complete_by.zone,
                    days_after=p.complete_by.days_after,
                )
                if p.complete_by
                else None
            ),
            on_overdue=p.on_overdue,
            stages=[stage_shape(stage) for stage in p.stages],
        )
        for p in module.pipelines
    ]


# 子阶段、固定来源和结果Data依赖均进入登记摘要，避免接口与worker拿不同配置。
def stage_shape(stage: Stage) -> dict[str, Any]:
    shape = dict(
        name=stage.name,
        operation=stage.operation.name,
        input_from=stage.input_from,
        wait=getattr(stage, "every", None),
        timeout=getattr(stage, "timeout", None),
        max_parallel=getattr(stage, "max_parallel", None),
        freeze_sources=stage.freeze_sources,
        source=stage.source.model_json_schema() if stage.source else None,
        members={name: model.model_json_schema() for name, model in stage.members.items()},
    )
    if isinstance(stage, FanOut):
        shape["stages"] = [stage_shape(child) for child in stage.stages]
        shape["join"] = [
            type(stage.join).__name__,
            getattr(stage.join, "success", 1),
            getattr(stage.join, "required", ()),
        ]
    return shape


# 只在使用新协议时扩展声明摘要，旧产品无协议的登记格式保持原样。
def endpoint_shapes(module: Module) -> dict[str, Any]:
    if not module.endpoints and not any(
        part.endpoints for flow in module.provides.values() for part in flow.steps
    ):
        return {}
    return {
        "endpoints": [e.shape() for e in sorted(module.endpoints, key=lambda e: e.name)],
        "step_endpoints": {
            item.name: {part.name: [e.name for e in part.endpoints] for part in flow.steps}
            for item, flow in module.provides.items()
        },
    }


# 额度与显式声明状态同入摘要，操作额度改变后旧声明证据会过期。
def query_budgets(module: Module) -> dict[str, Any]:
    return {
        item.name: dict(
            declared=item.query_budget is not None, **asdict(item.query_budget or DEFAULT_BUDGET)
        )
        for item in module.provides
    }
