from collections.abc import Iterator
from typing import Any

from fastapi_project.development.pipelines import memberships
from fastapi_project.development.query_budget import query_status

from shared.flow.step import source_of
from shared.graphs.static import flow_graph
from shared.modules.catalog import Catalog


def execution_counts(cases: list[dict[str, Any]], operation: str, step: str = "") -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in cases:
        if case["outcome"] != "passed":
            continue
        for run in case["runs"]:
            if run["operation"] != operation:
                continue
            statuses = (
                [item["status"] for item in run["steps"] if item["name"] == step]
                if step
                else [run["status"]]
            )
            for status in statuses:
                counts[status] = counts.get(status, 0) + 1
    return counts


def operation_status(
    catalog: Catalog, operation: str, cases: list[dict[str, Any]]
) -> dict[str, Any]:
    binding = catalog.by_name[operation]
    recent = last_run(cases, operation)
    steps = [
        {
            "name": part.name,
            "simulated": part.simulated,
            "title": part.title,
            "source": part.source,
            "calcs": [f"{func.__name__} · {source_of(func)}" for func in part.calcs],
            "rule": part.rule,
            "condition": part.when.title if part.when else "",
            "reads": list(part.reads),
            "writes": list(part.writes),
            "calls": [used.name for used in part.uses],
            "jobs": [used.name for used in part.later],
            "endpoints": [e.shape() for e in part.endpoints],
            "providers": [spec.shape() for spec in part.providers],
            "test_executions": execution_counts(cases, operation, part.name),
            "last_test": last_execution(cases, operation, part.name),
        }
        for part in binding.flow.steps
    ]
    return {
        **query_status(binding, cases, operation),
        "name": operation,
        "implementation": "skeleton" if any(p.simulated for p in binding.flow.steps) else "real",
        "providers": [spec.shape() for spec in binding.module.providers],
        "endpoints": [
            e.shape()
            for e in dict.fromkeys(e for part in binding.flow.steps for e in part.endpoints)
        ],
        "pipelines": memberships(catalog, operation),
        "title": binding.contract.title,
        "effect": binding.contract.effect or "unknown",
        "steps": steps,
        "graph": flow_graph(binding),
        "test_graph": flow_graph(binding, {step["name"]: step for step in recent["steps"]})
        if recent
        else None,
        "last_test_run": recent,
        "test_executions": execution_counts(cases, operation),
    }


def last_run(cases: list[dict[str, Any]], operation: str) -> dict[str, Any] | None:
    return next(passed_runs(cases, operation), None)


def passed_runs(cases: list[dict[str, Any]], operation: str) -> Iterator[dict[str, Any]]:
    for case in reversed(cases):
        if case["outcome"] != "passed":
            continue
        for run in reversed(case["runs"]):
            if run["operation"] == operation:
                yield run


def last_execution(cases: list[dict[str, Any]], operation: str, name: str) -> dict[str, Any] | None:
    for run in passed_runs(cases, operation):
        for step in reversed(run["steps"]):
            if step["name"] == name:
                return step
    return None
