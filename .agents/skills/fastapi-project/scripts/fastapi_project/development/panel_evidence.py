"""
面板状态只由当前源码和正式检查计算；规则确认与业务验收不混入绿色。
"""

from typing import Any

from fastapi_project.development.check_storage import load_cases
from fastapi_project.development.evidence import check_scope


# 真实调用方链参加整链覆盖，计划中尚不存在的依赖不能当作已经检查。
def callers(name: str, links: dict) -> set[str]:
    selected = {name}
    while True:
        expanded = selected | {
            source for source, targets in links.items() if selected & targets.keys()
        }
        if expanded == selected:
            return selected
        selected = expanded


# 框架级失败也保留，快速检查和未知范围不能提供正式完成证据。
def formal_checks(checks: list[dict], name: str) -> list[dict]:
    return [
        check
        for check in checks
        if name in check["fingerprints"]
        and check_scope(check)["kind"] in {"all", "module", "modules"}
    ]


# 每个相关包必须有实际测试，全部操作须执行通过，不能用空suite染绿。
def suite_covers(suite: dict, names: set[str], operations: set[str]) -> bool:
    if suite.get("exit_code") != 0:
        return False
    relevant = []
    for case in load_cases(suite):
        paths = tuple(
            f"tests/{folder}/{name}/" for name in names for folder in ("modules", "integration")
        )
        runs = case.get("runs", [])
        if case["nodeid"].startswith(paths) or any(
            run["operation"].partition(".")[0] in names for run in runs
        ):
            relevant.append(case)
    if not relevant or any(case["outcome"] != "passed" for case in relevant):
        return False
    runs = [run for case in relevant for run in case.get("runs", [])]
    if any(run.get("simulated") for run in runs):
        return False
    executed = {run["operation"] for run in runs if run["status"] == "ok"}
    return operations <= executed


# 同轮双库、实际调用链及当前全部相关源码一起判断，不拼接不同时间的成功。
def chain_passed(check: dict, names: set[str], modules: dict) -> bool:
    if not check["passed"] or check["source_changed"]:
        return False
    if any(check["fingerprints"].get(name) != modules[name]["fingerprint"] for name in names):
        return False
    operations = {item["name"] for name in names for item in modules[name]["operations"]}
    suites = {suite["database"]: suite for suite in check["suites"]}
    return all(
        database in suites and suite_covers(suites[database], names, operations)
        for database in ("sqlite", "postgresql")
    )


# 历史成功保留来源但不会冒充当前通过；最近三次均完整成功才显示稳定绿色。
def node_evidence(name: str, status: dict, checks: list[dict]) -> dict[str, Any]:
    module = status["modules"].get(name)
    if module is None:
        return {"state": "planned", "reason": "代码尚未登记", "flaky": False, "checks": []}
    selected = formal_checks(checks, name)
    current = [
        check
        for check in selected
        if not check["source_changed"] and check["fingerprints"][name] == module["fingerprint"]
    ]
    flaky = len({check["passed"] for check in current}) > 1
    result = {"flaky": flaky, "checks": [check["id"] for check in selected[-3:]]}
    if any(item["implementation"] == "skeleton" for item in module["operations"]):
        return {**result, "state": "skeleton", "reason": "仍有明确模拟步骤"}
    if selected and selected[-1] in current and not selected[-1]["passed"]:
        return {**result, "state": "failed", "reason": "最近当前版本正式检查失败"}
    if any(
        task["package"] == name and task["state"] != "complete" for task in status.get("tasks", [])
    ):
        return {**result, "state": "developing", "reason": "任务尚未完成或需要更新"}
    if not selected:
        return {**result, "state": "unknown", "reason": "没有正式检查证据"}
    if selected[-1] not in current:
        return {**result, "state": "stale", "reason": "最近检查不属于当前源码"}
    names = callers(name, status["dependencies"])
    stable = len(selected) >= 3 and all(
        chain_passed(check, names, status["modules"]) for check in selected[-3:]
    )
    if stable and not flaky:
        return {**result, "state": "stable", "reason": "当前包与调用链连续三次同轮双库通过"}
    return {
        **result,
        "state": "checked",
        "reason": "已有当前检查，整链连续三次双库稳定证据尚未齐全",
    }
