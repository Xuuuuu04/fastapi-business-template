"""
检查范围和测试来源版本：局部通过不能替代完整检查，跨包证据也要检查来源。
"""

import re
from typing import Any


# 只有确定属于某个业务包的测试才使用该包版本；框架测试使用整轮记录的版本范围。
def case_current(case: dict[str, Any], suite: dict[str, Any], versions: dict[str, str]) -> bool:
    if not suite["current"]:
        return False
    recorded = suite["fingerprints"]
    owner = re.match(r"^tests/(?:modules|integration)/([^/]+)/", case["nodeid"])
    if owner is not None:
        name = owner.group(1)
        return name in versions and recorded.get(name) == versions[name]
    return bool(recorded) and all(versions.get(name) == code for name, code in recorded.items())


# 老检查通过明确的检查项目识别范围，不用模块数量猜测一次局部测试是不是全量。
def check_scope(check: dict[str, Any]) -> dict[str, str]:
    if "scope" in check:
        return check["scope"]
    if "默认测试" in check["checks"]:
        return {"kind": "all"}
    if "模块测试" in check["checks"]:
        return {"kind": "module"}
    return {"kind": "unknown"}


# 保存最近完整检查；其后任何局部轮次都不能覆盖全局失败。
def latest_full_check(checks: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((check for check in reversed(checks) if check_scope(check)["kind"] == "all"), None)


# 全量结果只有包含全部当前模块且版本一致时，才适用于目前源码。
def full_check_current(check: dict[str, Any], versions: dict[str, str]) -> bool:
    return not check["source_changed"] and all(
        check["fingerprints"].get(name) == code for name, code in versions.items()
    )
