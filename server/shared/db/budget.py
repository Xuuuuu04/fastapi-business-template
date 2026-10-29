import logging
from dataclasses import asdict, dataclass
from typing import Any

from shared.errors.framework import StepRuleBroken
from shared.records.models import RunRecord

log = logging.getLogger("server.query_budget")


@dataclass(frozen=True)
class QueryBudget:
    queries: int = 1000
    rows: int = 100000
    bytes: int = 64000000
    repeated: int = 100


@dataclass(frozen=True)
class QueryPolicy:
    env: str = "local"
    mode: str = "auto"
    explain: bool = False

    def explain_enabled(self) -> bool:
        return self.env == "test" and self.explain


DEFAULT_BUDGET = QueryBudget()


def check_budget(budget: QueryBudget | None, name: str) -> list[str]:
    if budget is None:
        return []
    if not isinstance(budget, QueryBudget):
        return [f"操作 {name} 查询额度必须是 QueryBudget"]
    return [
        f"操作 {name} 查询额度 {key} 必须是正整数"
        for key, value in asdict(budget).items()
        if type(value) is not int or value <= 0
    ]


def policy(env: str, mode: str, declared: bool) -> str:
    if env == "production" or mode == "warn":
        return "warn"
    return "error" if env == "test" and (declared or mode == "error") else "warn"


def comparison(run: RunRecord, budget: QueryBudget, declared: bool) -> dict[str, Any]:
    actual = {
        key: sum(getattr(step, "database_" + key) for step in run.steps)
        for key in ("rows", "bytes")
    }
    actual["queries"] = sum(step.database_count for step in run.steps)
    unknown = {
        key: sum(getattr(step, "database_" + key + "_unknown") for step in run.steps)
        for key in ("rows", "bytes")
    }
    functions: dict[str, int] = {}
    locations = []
    for step in run.steps:
        for key, counts in step.database_functions.items():
            functions[key] = functions.get(key, 0) + counts["queries"]
            locations.append(dict(step=step.name, source=key, **counts))
    for child in [run.query_children] if run.query_children else []:
        for key in actual:
            actual[key] += child["actual"][key]
        for key in unknown:
            unknown[key] += child["unknown"][key]
        locations.extend(child["locations"])
        for location in child["locations"]:
            key = location["source"]
            functions[key] = functions.get(key, 0) + location["queries"]
    exceeded = [key for key, value in actual.items() if value > getattr(budget, key)]
    repeated = [
        dict(source=key, queries=count)
        for key, count in functions.items()
        if count > budget.repeated
    ]
    return dict(
        limits=asdict(budget),
        declared=declared,
        actual=actual,
        unknown=unknown,
        exceeded=exceeded,
        repeated=repeated,
        locations=locations,
        functions_complete=all(step.database_functions_complete for step in run.steps)
        and run.query_children.get("functions_complete", True),
    )


def evaluate(run: RunRecord, budget: QueryBudget, declared: bool, mode: str) -> None:
    run.query_budget = comparison(run, budget, declared) | {"mode": mode}
    issues = run.query_budget["exceeded"] or run.query_budget["repeated"]
    if not issues:
        return
    text = budget_text(run.query_budget)
    log.warning("query_budget run_id=%s %s", run.id, text)
    if mode == "error":
        raise StepRuleBroken(text)


def budget_text(result: dict[str, Any]) -> str:
    if not result:
        return "查询额度未知（旧记录没有保存额度数据）"
    actual, limits = result["actual"], result["limits"]
    names = {"queries": "查询", "rows": "行", "bytes": "内容"}
    counts = "，".join(
        f"{names[key]} {actual[key]}/{limits[key]}"
        + ("（部分未知）" if result["unknown"].get(key) else "")
        for key in ("queries", "rows", "bytes")
    )
    repeated = result["repeated"]
    parts = []
    if not result["functions_complete"]:
        parts.append("存储函数的统计不完整")
    parts.append(f"查询额度：{counts}；超额：{'、'.join(result['exceeded']) or '无'}")
    if repeated:
        first = repeated[0]
        parts.append(f"疑似在循环里逐行查询：{first['source']} 调用了 {first['queries']} 次")
    return "；".join(parts)


def merge_child(parent: RunRecord, child: RunRecord) -> None:
    result = child.query_budget
    if not result:
        return
    target = parent.query_children
    if not target:
        target.update(
            actual=dict(queries=0, rows=0, bytes=0),
            unknown=dict(rows=0, bytes=0),
            locations=[],
            functions_complete=True,
        )
    for kind in ("actual", "unknown"):
        for key, value in result[kind].items():
            target[kind][key] += value
    target["functions_complete"] &= result["functions_complete"]
    for location in result["locations"]:
        previous = next(
            (
                item
                for item in target["locations"]
                if item["source"] == location["source"] and item["step"] == location["step"]
            ),
            None,
        )
        if previous is not None:
            for key in ("queries", "rows", "bytes"):
                previous[key] += location[key]
        elif len(target["locations"]) < 200:
            target["locations"].append(dict(location))
        else:
            target["functions_complete"] = False


def prior_totals(run: RunRecord) -> dict[str, int]:
    fields = {"queries": "database_count", "rows": "database_rows", "bytes": "database_bytes"}
    children = run.query_children.get("actual", {})
    return {
        key: sum(getattr(step, field) for step in run.steps) + children.get(key, 0)
        for key, field in fields.items()
    }
