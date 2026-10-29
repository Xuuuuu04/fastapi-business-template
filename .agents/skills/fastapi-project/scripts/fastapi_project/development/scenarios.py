import re
from pathlib import Path
from typing import Any

from fastapi_docs.progress_doc import RULE_HEADING

STATUSES = ("passed", "failed", "skipped", "unrecorded")


def cells(line: str) -> list[str]:
    return [part.strip().replace(r"\|", "|") for part in re.split(r"(?<!\\)\|", line)[1:-1]]


def scenario_table(lines: list[str], start: int, path: Path) -> tuple[list[list[str]], int]:
    header = cells(lines[start])
    if not lines[start].rstrip().endswith("|") or header not in (
        ["样例编号", "输入", "结果"],
        ["样例编号", "情况", "结果"],
    ):
        raise ValueError(f"{path}:{start + 1}: 样例表必须以样例编号开头，后接输入或情况、结果")
    if start + 1 >= len(lines):
        raise ValueError(f"{path}:{start + 1}: 样例表缺少分隔行")
    separator_line = lines[start + 1].strip()
    separator = cells(separator_line)
    if (
        not separator_line.startswith("|")
        or not separator_line.endswith("|")
        or len(separator) != 3
        or not all(re.fullmatch(r":?-{3,}:?", cell) for cell in separator)
    ):
        raise ValueError(f"{path}:{start + 2}: 样例表分隔行错误")
    rows = []
    position = start + 2
    while position < len(lines) and lines[position].lstrip().startswith("|"):
        row = cells(lines[position])
        if not lines[position].rstrip().endswith("|") or len(row) != 3 or not all(row):
            raise ValueError(f"{path}:{position + 1}: 样例表应有三个非空单元格")
        rows.append(row)
        position += 1
    return rows, position


def declared_cases(path: Path, module: str) -> tuple[bool, list[dict[str, Any]]]:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    declared, rule, position = False, "", 0
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    while position < len(lines):
        line = lines[position]
        heading = RULE_HEADING.match(line)
        if line.startswith("#"):
            rule = heading.group(1) if heading else ""
        if line.lstrip().startswith("|") and "样例编号" in cells(line):
            rows, position = scenario_table(lines, position, path)
            declared = True
            for identity, title, expected in rows:
                if not re.fullmatch(r"R-\d+-C\d+", identity) or not identity.startswith(
                    rule + "-C"
                ):
                    raise ValueError(f"{path}: 样例 {identity} 不属于当前规则 {rule or '未声明'}")
                if identity in seen:
                    raise ValueError(f"{path}: 重复样例编号 {identity}")
                seen.add(identity)
                cases.append(
                    {
                        "id": f"{module}.{identity}",
                        "rule": rule,
                        "title": title,
                        "expected": expected,
                    }
                )
        else:
            position += 1
    return declared, cases


def evidence_status(evidence: list[dict[str, Any]]) -> str:
    outcomes = {case["outcome"] for case in evidence}
    if "failed" in outcomes:
        return "failed"
    if "skipped" in outcomes:
        return "skipped"
    return "passed" if outcomes == {"passed"} else "unrecorded"


def database_case(identity: str, suite: dict[str, Any]) -> dict[str, Any]:
    evidence = [case for case in suite["cases"] if identity in case.get("scenario_ids", [])]
    current = suite["current"] and all(case.get("current", True) for case in evidence)
    return {
        "current": current,
        "status": evidence_status(evidence) if current else "unrecorded",
        "nodeids": sorted({case["nodeid"] for case in evidence}),
        "outcomes": {case["nodeid"]: case["outcome"] for case in evidence},
    }


def database_check(suite: dict[str, Any]) -> dict[str, Any]:
    return {
        "current": suite["current"],
        "source_changed": suite.get("source_changed"),
        "exit_code": suite["exit_code"],
        "suite_passed": suite["exit_code"] == 0,
        "checks_passed": suite["checks_passed"],
        "finished_at": suite.get("finished_at"),
    }


def scenario_status(project: Path, module: str, tests: dict[str, Any]) -> dict[str, Any]:
    declared, cases = declared_cases(project / "doc" / module / "rules.md", module)
    latest = tests.get("latest", {})
    for case in cases:
        case["by_database"] = {
            database: database_case(case["id"], suite) for database, suite in latest.items()
        }
    identities = {case["id"] for case in cases}
    unknown = {
        identity
        for suite in latest.values()
        for case in suite["cases"]
        for identity in case.get("scenario_ids", [])
        if identity.startswith(module + ".") and identity not in identities
    }
    counts = {
        database: {
            "planned": len(cases),
            **{
                status: sum(case["by_database"][database]["status"] == status for case in cases)
                for status in STATUSES
            },
        }
        for database in latest
    }
    return {
        "declared": declared,
        "note": "样例声明不代替规则；没有声明不等于没有规则。",
        "cases": cases,
        "counts_by_database": counts,
        "checks_by_database": {db: database_check(suite) for db, suite in latest.items()},
        "unknown_ids": sorted(unknown),
    }
