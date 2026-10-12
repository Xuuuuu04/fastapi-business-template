"""
节点检查详情只保留范围、数据库计数和时间，完整运行值仍在本机原件中。
"""

from fastapi_project.development.check_storage import load_cases
from fastapi_project.development.panel_evidence import formal_checks
from fastapi_project.development.status import relevant_cases


# 最近三次实际检查分别列出，当前性只说明本包源码，不把局部结果写成全局成功。
def recent_records(name: str, status: dict, checks: list[dict]) -> list[dict]:
    result: list[dict] = []
    module = status["modules"].get(name)
    if not module:
        return result
    for check in formal_checks(checks, name)[-3:]:
        suites = []
        for suite in check["suites"]:
            cases = relevant_cases({**suite, "cases": load_cases(suite)}, name)
            suites.append(
                {
                    "database": suite["database"],
                    "exit_code": suite.get("exit_code"),
                    "counts": {
                        outcome: sum(case["outcome"] == outcome for case in cases)
                        for outcome in ("passed", "failed", "skipped")
                    },
                    "test_seconds": round(
                        sum(sum(case.get("durations", {}).values()) for case in cases), 4
                    ),
                }
            )
        result.append(
            {
                "id": check["id"],
                "finished_at": check["finished_at"],
                "scope": check.get("scope", {"kind": "unknown"}),
                "current_module": not check["source_changed"]
                and check["fingerprints"][name] == module["fingerprint"],
                "passed": check["passed"],
                "elapsed_seconds": check.get("elapsed_seconds"),
                "suites": suites,
            }
        )
    return result
