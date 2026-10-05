"""
给主代理的决策摘要：保留计划缺项、待确认和检查状态，具体步骤与运行按需读取。
完整项目状态仍由 status.py 提供；这里不复制完整测试记录，也不推测业务已验收。
"""

import shlex
from typing import Any

from tools.development.attention import attention, plan_summary
from tools.development.evidence import check_scope

PROBLEM_LIMIT = 5


# 生成可直接在 server 目录执行的下一步命令。
def command(*arguments: str) -> str:
    return shlex.join(["uv", "run", "python", "-m", "tools.project", *arguments])


# 各数据库分别保留新旧状态；问题过多时说明总数和省略数量。
def test_summary(tests: dict[str, Any]) -> dict[str, Any]:
    latest = {}
    for database, suite in tests["latest"].items():
        problems = [
            case
            for case in suite["cases"]
            if case["outcome"] != "passed" or case.get("current") is False
        ]
        problems.sort(key=lambda case: {"failed": 0, "skipped": 1}.get(case["outcome"], 2))
        latest[database] = {
            key: suite[key]
            for key in ("finished_at", "current", "checks_passed", "exit_code", "counts")
        }
        latest[database].update(
            problem_count=len(problems),
            problems=[
                {
                    "nodeid": case["nodeid"],
                    "outcome": case["outcome"],
                    **({"current": case["current"]} if "current" in case else {}),
                    "next": command("--test", case["nodeid"], "--json"),
                }
                for case in problems[:PROBLEM_LIMIT]
            ],
            omitted_problems=max(0, len(problems) - PROBLEM_LIMIT),
        )
        if "fingerprints" in suite:
            latest[database]["current_counts"] = {
                outcome: sum(
                    case["outcome"] == outcome and case["current"] for case in suite["cases"]
                )
                for outcome in ("passed", "failed", "skipped")
            }
            latest[database]["stale_count"] = sum(not case["current"] for case in suite["cases"])
    return {"rounds": tests["rounds"], "latest": latest}


# 模块摘要只展开操作入口；规则样例明细仅在单模块摘要中显示。
def module_summary(module: dict[str, Any], *, details: bool = False) -> dict[str, Any]:
    result = {key: module[key] for key in ("name", "title", "enabled", "code", "pending")}
    result.update(
        rule_count=len(module["rules"]),
        annotation_count=len(module["test_annotations"]),
        tests=test_summary(module["tests"]),
        operations=[
            {
                "name": item["name"],
                "title": item["title"],
                "steps": len(item["steps"]),
                "test_executions": item["test_executions"],
                "next": command("--operation", item["name"], "--json"),
            }
            for item in module["operations"]
        ],
        next=command("--module", module["name"], "--summary", "--json"),
    )
    if not details:
        result["operation_count"] = len(result.pop("operations"))
    if "scenarios" in module:
        result["scenarios"] = {
            key: value for key, value in module["scenarios"].items() if details or key != "cases"
        }
    return result


# 可选数据库查询只列运行编号与结果，不把所有运行的步骤再展开。
def runtime_summary(runtime: dict[str, Any] | None) -> dict[str, Any] | None:
    if runtime is None:
        return None
    return {key: value for key, value in runtime.items() if key not in ("runs", "graph")} | {
        "runs": [
            {key: run[key] for key in ("id", "operation", "status")} for run in runtime["runs"]
        ]
    }


# 单包摘要保留计划缺项，尚未登记的包也能按需读取。
def package_summary(status: dict[str, Any], module: str) -> dict[str, Any]:
    package = next(
        (item for line in status["lines"] for item in line["packages"] if item["module"] == module),
        None,
    )
    if module in status["modules"]:
        result = module_summary(status["modules"][module], details=True)
        result["plan"] = package
        result["dependencies"] = status["dependencies"].get(module, {})
    elif package is not None:
        result = {
            "name": module,
            "title": package["title"],
            "registered": False,
            "plan": package,
        }
    else:
        raise ValueError(f"模块未列入计划且尚未登记：{module}")
    return result


# 完整 JSON 保持原用法；摘要是独立视图，不修改原始证据。
def project_summary(status: dict[str, Any], module: str = "") -> dict[str, Any]:
    if module:
        result = package_summary(status, module)
    else:
        result = {
            key: status[key]
            for key in (
                "schema_version",
                "name",
                "has_plan",
                "lines",
                "totals",
                "ratios",
                "unplanned_modules",
                "check_rounds",
                "latest_check",
                "latest_full_check",
            )
        }
        result["lines"] = plan_summary(status["lines"])
        result["modules"] = {name: module_summary(item) for name, item in status["modules"].items()}
        result["dependencies"] = {
            caller: {
                provider: {"operation_title_count": len(titles)}
                for provider, titles in providers.items()
            }
            for caller, providers in status["dependencies"].items()
        }
        result["attention"] = attention(status)
    return {
        "view": "summary",
        **result,
        "runtime": runtime_summary(status["runtime"]),
        "meaning": "登记、测试成功执行和业务验收分开判断；测试标注不证明业务正确。",
    }


# 一次只读取一个公开操作的图、步骤与最近实际测试。
def selected_operation(status: dict[str, Any], name: str) -> dict[str, Any]:
    module_name = name.partition(".")[0]
    module = status["modules"].get(module_name)
    if module is not None:
        for operation in module["operations"]:
            if operation["name"] == name:
                return {
                    "view": "operation",
                    "module": module_name,
                    "code": module["code"],
                    "checks": test_summary(module["tests"]),
                    **operation,
                }
    raise ValueError(f"操作尚未登记：{name}；请先查看项目摘要")


# 每种数据库分别查找该测试的最近执行，包含框架测试且不复制跨模块记录。
def selected_test(
    status: dict[str, Any], nodeid: str, module: str, checks: list[dict[str, Any]]
) -> dict[str, Any]:
    records = {}
    for check in checks:
        if module and module not in check["fingerprints"]:
            continue
        for suite in check["suites"]:
            case = next((item for item in suite["cases"] if item["nodeid"] == nodeid), None)
            if case is None:
                continue
            versions = {
                name: {
                    "current": check["fingerprints"][name] == item["fingerprint"]
                    and not check["source_changed"]
                }
                for name, item in status["modules"].items()
                if name in check["fingerprints"]
            }
            records[suite["database"]] = {
                "database": suite["database"],
                "finished_at": check["finished_at"],
                "checks_passed": check["passed"],
                "scope": check_scope(check),
                "exit_code": suite["exit_code"],
                "source_changed": check["source_changed"],
                "modules": versions,
                "case": case,
            }
    if not records:
        raise ValueError(f"留存检查中没有测试记录：{nodeid}")
    return {"view": "test", "nodeid": nodeid, "records": list(records.values())}


# 模块一页列出待确认、各数据库状态和继续读取的入口。
def module_markdown_summary(module: dict[str, Any]) -> list[str]:
    lines = [
        f"## {module['title']}（{module['name']}）",
        f"启用：{module['enabled']}；规则 {module['rule_count']}；"
        f"待确认 {len(module['pending'])}。",
    ]
    lines.extend(f"- 待确认：{text}" for text in module["pending"])
    for database, suite in module["tests"]["latest"].items():
        lines.append(
            f"- {database}：{'当前' if suite['current'] else '过期'}；"
            f"该轮检查{'通过' if suite['checks_passed'] else '失败'}；{suite['counts']}"
        )
        lines.append(
            f"  - 当前来源结果：{suite['current_counts']}；过期来源 {suite['stale_count']} 项。"
        )
        lines.extend(
            f"  - {item['outcome']}"
            + ("（来源过期）" if item.get("current") is False else "")
            + f"：{item['nodeid']}；{item['next']}"
            for item in suite["problems"]
        )
        if suite["omitted_problems"]:
            lines.append(f"  - 另有 {suite['omitted_problems']} 项，请读取模块完整记录。")
    lines.append(f"下一步：{module['next']}")
    if "scenarios" in module:
        lines.append(f"规则样例实际执行：{module['scenarios']['counts_by_database']}")
    return lines


# 简短文本与 JSON 使用同一摘要，失败、过期和待确认均不被成功数量遮住。
def summary_markdown(summary: dict[str, Any]) -> str:
    lines = [f"# {summary.get('title', summary['name'])}：主代理摘要", ""]
    if summary.get("registered") is False:
        return (
            "\n".join(
                [
                    *lines,
                    "开发包已列入计划，代码尚未登记。",
                    *summary["plan"]["missing"],
                    summary["meaning"],
                ]
            )
            + "\n"
        )
    check = summary.get("latest_check")
    if check is not None:
        lines.append(
            f"最近留存检查：{'通过' if check['passed'] else '失败'}；"
            f"源码在检查中{'发生变化' if check['source_changed'] else '未改变'}。"
        )
        lines.append(f"检查项目：{check['checks']}")
        lines.append(
            f"检查范围：{check.get('scope', {'kind': 'unknown'})}；快速检查不代表正式验收。"
        )
        if check.get("elapsed_seconds") is not None:
            lines.append(f"本轮耗时：{check['elapsed_seconds']} 秒。")
    lines.extend(
        f"需处理：{item['module']} {item['message']}" for item in summary.get("attention", [])
    )
    modules = summary.get("modules", {summary["name"]: summary})
    for module in modules.values():
        lines += ["", *module_markdown_summary(module)]
    for line in summary.get("lines", []):
        for package in line["packages"]:
            if package["missing"]:
                lines.append(f"尚未登记：{', '.join(package['missing'])}")
            if package["omitted_missing"]:
                lines.append(f"另有 {package['omitted_missing']} 项；{package['next']}")
    return "\n".join([*lines, "", summary["meaning"]]) + "\n"
