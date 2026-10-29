from typing import Any

PREVIEW_LIMIT = 5


def plan_summary(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for line in lines:
        packages = []
        for package in line["packages"]:
            packages.append(
                {
                    "module": package["module"],
                    "title": package["title"],
                    "enabled": package["enabled"],
                    "counts": {
                        key: len(package[key])
                        for key in ("planned", "registered", "test_successful", "missing", "extra")
                    },
                    "missing": package["missing"][:PREVIEW_LIMIT],
                    "omitted_missing": max(0, len(package["missing"]) - PREVIEW_LIMIT),
                    "next": f"uv run dev status --module {package['module']} --summary --json",
                }
            )
        result.append({"name": line["name"], "packages": packages})
    return result


def module_attention(module: dict[str, Any]) -> list[dict[str, str]]:
    name = module["name"]
    result = []
    if module["pending"]:
        result.append(
            {
                "kind": "pending",
                "module": name,
                "message": f"有 {len(module['pending'])} 项业务问题需要确认",
            }
        )
    latest = module["tests"]["latest"]
    if not latest:
        result.append({"kind": "unrecorded", "module": name, "message": "没有模块检查记录"})
    for database, suite in latest.items():
        if not suite["current"]:
            result.append(
                {
                    "kind": "stale",
                    "module": name,
                    "message": f"{database} 检查已过期，需按当前源码重跑",
                }
            )
        if suite["current"] and any(case.get("current") is False for case in suite["cases"]):
            result.append(
                {
                    "kind": "stale_source",
                    "module": name,
                    "message": f"{database} 有测试来源已改变，相关旧结果不能证明当前代码",
                }
            )
        if suite["current"] and not suite["checks_passed"]:
            result.append(
                {"kind": "failed", "module": name, "message": f"{database} 所属检查轮次未通过"}
            )
    return result


def attention(status: dict[str, Any]) -> list[dict[str, str]]:
    result = []
    full = status["latest_full_check"]
    if full is None:
        result.append({"kind": "full_check", "module": "", "message": "没有完整的全量检查记录"})
    elif not full["passed"] or not full["current"]:
        result.append({"kind": "full_check", "module": "", "message": "最近全量检查失败或已过期"})
    check = status["latest_check"]
    if check is not None and (not check["passed"] or check["source_changed"]):
        result.append({"kind": "check", "module": "", "message": "最近检查失败或运行期间源码改变"})
    for module in status["modules"].values():
        result.extend(module_attention(module))
    for line in status["lines"]:
        for package in line["packages"]:
            if package["missing"]:
                result.append(
                    {
                        "kind": "missing",
                        "module": package["module"],
                        "message": f"计划中 {len(package['missing'])} 个操作尚未登记",
                    }
                )
    return result
