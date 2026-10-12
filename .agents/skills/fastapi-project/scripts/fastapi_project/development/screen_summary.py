"""
全项目文本摘要限定一屏：模块各一行，未展开的信息通过模块/操作查看，不隐藏总数。
每行写成完整的话，让第一次读的人不用解码。
"""

from typing import Any


# 每个数据库的检查状态写成一句话：版本新旧、是否通过、通过多少。
def suite_text(database: str, suite: dict[str, Any]) -> str:
    age = "当前版本" if suite["current"] else "过期版本（源码已经变了，需要重新检查）"
    result = "通过" if suite["checks_passed"] else "没有通过"
    return f"{database} 上最近一轮检查：{age}，{result}（{suite['counts']}）"


# 只显示最需要下一步行动的信息，完整JSON及单模块视图仍保留详情。
def render(summary: dict[str, Any]) -> str:
    lines = [f"# {summary['name']}：项目摘要"]
    check = summary.get("latest_full_check") or summary.get("latest_check")
    if check:
        verdict = "通过" if check.get("passed") else "没有通过（或结果未知）"
        lines.append(f"最近一次检查：{verdict}，范围是{check.get('scope', '完整记录')}。")
    for item in summary.get("attention", [])[:3]:
        lines.append(f"需要处理：{item['module']}——{item['message']}")
    modules = list(summary.get("modules", {}).values())
    for module in modules[:12]:
        latest = module["tests"]["latest"]
        states = "；".join(suite_text(db, suite) for db, suite in latest.items())
        lines.append(
            f"- **{module['title']}**（{module['name']}）：{module['operation_count']} 个操作，"
            f"{'启用中' if module['enabled'] else '已关闭'}，"
            f"{len(module['pending'])} 件事待确认；{states or '还没有检查记录'}。"
        )
    if len(modules) > 12:
        more = len(modules) - 12
        lines.append(f"另外还有 {more} 个模块没有列出来，需要时用 --module 或 --json 查看。")
    pipelines = summary.get("pipelines", [])
    for pipeline in pipelines[:5]:
        last = pipeline.get("last")
        if last:
            state = f"当前在“{last['current_stage']}”阶段，状态 {last['state']}"
        else:
            state = "没有查到运行记录"
        lines.append(f"- 流程 {pipeline['name']}：{state}。{pipeline['evidence']}")
    if len(pipelines) > 5:
        more = len(pipelines) - 5
        lines.append(f"另外还有 {more} 个流程没有列出来，需要时用 --module 或 --json 查看。")
    missing = sum(
        len(package["missing"]) + package["omitted_missing"]
        for line in summary.get("lines", [])
        for package in line["packages"]
    )
    if missing:
        lines.append(f"计划里还有 {missing} 个操作没有登记，用 --module 查看具体是哪些。")
    lines += [
        "想看细节：--module 模块名 --summary，或 --operation 完整操作名。",
        "提醒：登记了多少、测试是否通过、业务是否验收，是三件不同的事，要分别确认。",
    ]
    return "\n".join(lines[:28]) + "\n"


# 模块一页列出待确认、各数据库状态和继续读取的入口。
def module_markdown_summary(module: dict[str, Any]) -> list[str]:
    lines = [
        f"## {module['title']}（{module['name']}）",
        f"当前{'启用' if module['enabled'] else '关闭'}；共 {module['rule_count']} 条规则，"
        f"其中 {len(module['pending'])} 件事待确认。",
    ]
    lines.extend(f"- 待确认：{text}" for text in module["pending"])
    for database, suite in module["tests"]["latest"].items():
        age = "当前版本" if suite["current"] else "过期版本"
        verdict = "通过" if suite["checks_passed"] else "失败"
        lines.append(f"- {database}：{age}，这轮检查{verdict}（{suite['counts']}）。")
        lines.append(
            f"  - 其中当前版本的结果：{suite['current_counts']}；"
            f"另有 {suite['stale_count']} 项来自过期版本。"
        )
        lines.extend(
            f"  - {item['outcome']}"
            + ("（这条来自过期版本）" if item.get("current") is False else "")
            + f"：{item['nodeid']}；{item['next']}"
            for item in suite["problems"]
        )
        if suite["omitted_problems"]:
            more = suite["omitted_problems"]
            lines.append(f"  - 另有 {more} 项问题没有展开，请读取模块完整记录。")
    lines.append(f"下一步：{module['next']}")
    if "scenarios" in module:
        lines.append(f"规则样例实际执行：{module['scenarios']['counts_by_database']}")
    return lines
