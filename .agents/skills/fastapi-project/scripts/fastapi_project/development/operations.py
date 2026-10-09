"""
单个操作的声明、上游协议与实际测试执行证据，未执行的信息保持未知。
"""

from collections.abc import Iterator
from typing import Any

from fastapi_project.development.pipelines import memberships

from shared.graphs.static import flow_graph
from shared.modules.catalog import Catalog


# 按实际结束状态统计执行次数；错误场景测试中的业务失败不会变成测试失败。
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


# 一个操作的步骤图与当前位置，全部来自真实模块声明。
def operation_status(
    catalog: Catalog, operation: str, cases: list[dict[str, Any]]
) -> dict[str, Any]:
    binding = catalog.by_name[operation]
    recent = last_run(cases, operation)
    steps = [
        {
            "name": part.name,
            "title": part.title,
            "source": part.source,
            "rule": part.rule,
            "condition": part.when.title if part.when else "",
            "reads": list(part.reads),
            "writes": list(part.writes),
            "calls": [used.name for used in part.uses],
            "jobs": [used.name for used in part.later],
            "endpoints": [e.shape() for e in part.endpoints],
            "test_executions": execution_counts(cases, operation, part.name),
            "last_test": last_execution(cases, operation, part.name),
        }
        for part in binding.flow.steps
    ]
    return {
        "name": operation,
        "endpoints": [
            e.shape()
            for e in dict.fromkeys(e for part in binding.flow.steps for e in part.endpoints)
        ],
        "pipelines": memberships(catalog, operation),
        "title": binding.contract.title,
        "steps": steps,
        "graph": flow_graph(binding),
        "test_graph": flow_graph(binding, {step["name"]: step for step in recent["steps"]})
        if recent
        else None,
        "last_test_run": recent,
        "test_executions": execution_counts(cases, operation),
    }


# 按最近测试的实际运行显示整条路径，不能把多次执行拼成一次成功。
def last_run(cases: list[dict[str, Any]], operation: str) -> dict[str, Any] | None:
    return next(passed_runs(cases, operation), None)


# 从最近到最早遍历实际通过的测试，失败和跳过的测试不会提供成功证据。
def passed_runs(cases: list[dict[str, Any]], operation: str) -> Iterator[dict[str, Any]]:
    for case in reversed(cases):
        if case["outcome"] != "passed":
            continue
        for run in reversed(case["runs"]):
            if run["operation"] == operation:
                yield run


# 最近一次通过测试中的实际步骤记录；老记录缺少时间时保持未知。
def last_execution(cases: list[dict[str, Any]], operation: str, name: str) -> dict[str, Any] | None:
    for run in passed_runs(cases, operation):
        for step in reversed(run["steps"]):
            if step["name"] == name:
                return step
    return None
