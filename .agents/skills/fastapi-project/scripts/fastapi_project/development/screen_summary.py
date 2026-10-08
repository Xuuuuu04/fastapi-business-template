"""
全项目文本摘要限定一屏：模块各一行，未展开的信息通过模块/操作查看，不隐藏总数。
"""

from typing import Any


# 只显示最需要下一步行动的信息，完整JSON及单模块视图仍保留详情。
def render(summary: dict[str, Any]) -> str:
    lines = [f"# {summary['name']}：项目摘要"]
    check = summary.get("latest_full_check") or summary.get("latest_check")
    if check:
        lines.append(
            f"最近检查：{'通过' if check.get('passed') else '未通过或未知'}；"
            f"范围{check.get('scope', '完整记录')}。"
        )
    for item in summary.get("attention", [])[:3]:
        lines.append(f"需处理：{item['module']} {item['message']}")
    modules = list(summary.get("modules", {}).values())
    for module in modules[:12]:
        states = []
        for database, suite in module["tests"]["latest"].items():
            states.append(f"{database}:{'当前' if suite['current'] else '过期'}{suite['counts']}")
        lines.append(
            f"{module['name']}：{module['title']}；操作{module['operation_count']}；"
            f"{'启用' if module['enabled'] else '关闭'}；待确认{len(module['pending'])}；"
            f"{'；'.join(states) or '检查未知'}"
        )
    if len(modules) > 12:
        lines.append(f"另有{len(modules) - 12}模块，使用--json或--module深入。")
    pipelines = summary.get("pipelines", [])
    for pipeline in pipelines[:5]:
        last = pipeline.get("last")
        state = f"{last['current_stage']}/{last['state']}" if last else "运行未知"
        lines.append(f"流程 {pipeline['name']}：{state}；{pipeline['evidence']}")
    if len(pipelines) > 5:
        lines.append(f"另有{len(pipelines) - 5}流程，使用--module或--json深入。")
    missing = sum(
        len(package["missing"]) + package["omitted_missing"]
        for line in summary.get("lines", [])
        for package in line["packages"]
    )
    if missing:
        lines.append(f"计划尚缺{missing}操作；使用--module检查具体项。")
    lines += [
        "深入：--module 模块名 --summary；--operation 完整操作名。",
        "登记、测试和业务验收分别判断。",
    ]
    return "\n".join(lines[:28]) + "\n"


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
