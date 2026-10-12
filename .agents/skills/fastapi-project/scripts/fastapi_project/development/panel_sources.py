"""
面板规模、指标与待处理资料来自已有文件，只导出摘要，不复制原话或运行值。
"""

import json
from pathlib import Path

from fastapi_project.development.check_storage import load_cases
from fastapi_project.development.evidence import latest_full_check
from fastapi_project.development.ledger import read_ledger

SIZE_LIMITS = {"lines": 1000, "steps": 20, "dependencies": 8}


# 备注只作文字展示，不参加代码指纹或检查颜色；原件保留在忽略目录。
def package_note(project: Path, name: str) -> str:
    path = project / ".agents/records/notes" / (name + ".md")
    if path.is_symlink():
        return "备注是链接，未读取。"
    return path.read_text()[:4000] if path.is_file() else ""


# 包规模是整理建议，与框架单文件和函数质量阈值分开，不降低已有检查要求。
def package_size(project: Path, name: str, module: dict, links: dict) -> dict:
    folder = (
        project / "server" / ("library" if module.get("kind") == "library" else "service") / name
    )
    paths = [
        path
        for path in folder.rglob("*.py")
        if not path.is_symlink() and "__pycache__" not in path.parts
    ]
    size = {
        "lines": sum(len(path.read_text().splitlines()) for path in paths),
        "steps": sum(len(operation["steps"]) for operation in module.get("operations", [])),
        "dependencies": len(links.get(name, {})),
    }
    return {
        **size,
        "thresholds": SIZE_LIMITS,
        "suggest_split": any(size[key] > limit for key, limit in SIZE_LIMITS.items()),
    }


# 本机请求与审查单只列明确字段，损坏资料保留文件和错误说明。
def pending_records(project: Path, folder: str, fields: tuple[str, ...]) -> list[dict]:
    result = []
    for path in sorted((project / ".agents/records" / folder).glob("*.json")):
        try:
            data = json.loads(path.read_text())
            if not isinstance(data, dict):
                raise ValueError("资料必须为对象")
            result.append(
                {key: data.get(key) for key in fields}
                | {"file": path.relative_to(project).as_posix()}
            )
        except (ValueError, OSError):
            result.append(
                {
                    "file": path.relative_to(project).as_posix(),
                    "warning": "资料无法读取，请核对原件",
                }
            )
    return result


# 高风险待确认优先列出，业务原文和本机来源档案不会进入HTML。
def attention(project: Path) -> dict:
    ledger = read_ledger(project)
    rules = [rule for rule in ledger.rules if rule.state not in {"confirmed", "retired"}]
    rules.sort(key=lambda rule: ({"high": 0, "medium": 1, "low": 2}[rule.risk], rule.id))
    return {
        "rules": [
            {"id": rule.id, "risk": rule.risk, "state": rule.state, "revision": rule.revision}
            for rule in rules
        ],
        "contract_requests": pending_records(
            project, "contract-requests", ("id", "package", "state", "reason", "suggestion")
        ),
        "reviews": pending_records(project, "reviews", ("task", "state", "outside", "problems")),
    }


# 时间曲线与通过率保留范围，最慢测试只取最近完整轮，不把不同库合成一项。
def metrics(checks: list[dict], project: Path) -> dict:
    complete = [check for check in checks if check.get("scope", {}).get("kind") == "all"]
    latest = latest_full_check(checks)
    slow = []
    if latest:
        for suite in latest["suites"]:
            for case in load_cases(suite):
                slow.append(
                    {
                        "test": case["nodeid"],
                        "database": suite["database"],
                        "seconds": round(sum(case.get("durations", {}).values()), 4),
                        "outcome": case["outcome"],
                    }
                )
    slow.sort(key=lambda item: item["seconds"], reverse=True)
    rules = read_ledger(project).rules
    return {
        "rounds": len(complete),
        "pass_rate": sum(check["passed"] for check in complete) / len(complete)
        if complete
        else None,
        "history": [
            {
                key: check.get(key)
                for key in ("id", "finished_at", "elapsed_seconds", "passed", "source_changed")
            }
            for check in complete[-30:]
        ],
        "slow_tests": slow[:10],
        "rules": {
            state: sum(rule.state == state for rule in rules)
            for state in ("inferred", "adopted", "confirmed", "retired")
        },
    }
