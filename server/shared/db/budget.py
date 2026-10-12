"""
操作查询额度声明与运行结束对比；未知测量不伪装成零，生产不打断。
"""

import logging
from dataclasses import asdict, dataclass
from typing import Any

from shared.errors.framework import StepRuleBroken
from shared.records.models import RunRecord

log = logging.getLogger("server.query_budget")


# 额度按单次操作/分段运行计算；次数包含Db读写，rows包含返回/修改行数。
@dataclass(frozen=True)
class QueryBudget:
    queries: int = 1000
    rows: int = 100000
    bytes: int = 64000000
    repeated: int = 100


# 环境配置与业务额度分开；生产始终只记录，EXPLAIN只允许测试环境。
@dataclass(frozen=True)
class QueryPolicy:
    env: str = "local"
    mode: str = "auto"
    explain: bool = False

    # 诊断开关不能在生产开启。
    def explain_enabled(self) -> bool:
        return self.env == "test" and self.explain


DEFAULT_BUDGET = QueryBudget()


# 启动时校验声明，错误汇总到操作名，不允许负值、布尔或错误类型。
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


# 默认宽松只警告；显式声明后测试默认失败，可选择warn或把默认约束升级为error。
def policy(env: str, mode: str, declared: bool) -> str:
    if env == "production" or mode == "warn":
        return "warn"
    return "error" if env == "test" and (declared or mode == "error") else "warn"


# 每步骤累计不依赖有限SQL明细，最近记录/演练共用相同结构。
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


# 正常执行后在提交前检查，失败执行只附事实，不覆盖原异常。
def evaluate(run: RunRecord, budget: QueryBudget, declared: bool, mode: str) -> None:
    run.query_budget = comparison(run, budget, declared) | {"mode": mode}
    issues = run.query_budget["exceeded"] or run.query_budget["repeated"]
    if not issues:
        return
    text = budget_text(run.query_budget)
    log.warning("query_budget run_id=%s %s", run.id, text)
    if mode == "error":
        raise StepRuleBroken(text)


# 摘要只放总量和超额/循环提示，存储函数位置仍在结构化记录中。
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


# 子操作总量累加，最多保留200种步骤/函数位置，不随循环调用次数增长。
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


# 每步骤开始只保存先前总量，计划诊断按操作累计额度判断，不复制先前SQL明细。
def prior_totals(run: RunRecord) -> dict[str, int]:
    fields = {"queries": "database_count", "rows": "database_rows", "bytes": "database_bytes"}
    children = run.query_children.get("actual", {})
    return {
        key: sum(getattr(step, field) for step in run.steps) + children.get(key, 0)
        for key, field in fields.items()
    }
