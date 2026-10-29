from dataclasses import asdict
from typing import Any

from shared.db.budget import DEFAULT_BUDGET
from shared.modules.catalog import Binding


def query_status(binding: Binding, cases: list[dict[str, Any]], operation: str) -> dict[str, Any]:
    return dict(
        query_budget=dict(
            declared=binding.contract.query_budget is not None,
            **asdict(binding.contract.query_budget or DEFAULT_BUDGET),
        ),
        query_actual=latest_query(cases, operation),
    )


def latest_query(cases: list[dict[str, Any]], operation: str) -> dict[str, Any]:
    for case in reversed(cases):
        for run in reversed(case.get("runs", [])):
            if run["operation"] == operation:
                return dict(
                    measured=run.get("query_budget") or "未知",
                    run_id=run.get("id", "未知"),
                    status=run.get("status", "未知"),
                    outcome=case["outcome"],
                    current=case.get("current"),
                    started_at=run.get("started_at", "未知"),
                )
    return dict(measured="未知")
