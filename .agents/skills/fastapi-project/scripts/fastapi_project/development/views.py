from typing import Any

from shared.graphs.mermaid import label, node_id


def project_graph(status: dict[str, Any]) -> str:
    lines = ["flowchart TD", f'    root["{label(status["name"])}"]']
    for index, line in enumerate(status["lines"]):
        parent = f"line{index}"
        lines += [f'    {parent}["{label(line["name"])}"]', f"    root --> {parent}"]
        for package in line["packages"]:
            child = node_id("m", package["module"])
            text = (
                f"{package['title']}：登记 {len(package['registered'])}/{len(package['planned'])}，"
                f"测试成功执行 {len(package['test_successful'])}/{len(package['planned'])}"
            )
            lines += [f'    {child}["{label(text)}"]', f"    {parent} --> {child}"]
    for name in status["unplanned_modules"]:
        child = node_id("m", name)
        lines += [
            f'    {child}["{label(status["modules"][name]["title"])}（未列入计划）"]',
            f"    root --> {child}",
        ]
    lines += [line for line in status["module_graph"].splitlines()[1:] if " -->|" in line]
    return "\n".join(lines)


def cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def project_markdown(status: dict[str, Any]) -> str:
    lines = [f"# {cell(status['name'])}：开发状态", ""]
    totals = status["totals"]
    if totals:
        lines += [
            f"计划 {totals['planned']} 个操作；已登记 {totals['registered']}；"
            f"当前代码在测试中成功执行 {totals['test_successful']}。",
            "",
        ]
    else:
        lines += ["尚未填写项目计划，完成比例未知。", ""]
    lines += check_summary(status["latest_check"])
    lines += [
        f"本机保留 {status['check_rounds']} 轮检查。登记表示代码结构存在；"
        "成功执行表示测试样例经过该操作。",
        "",
        "```mermaid",
        project_graph(status),
        "```",
        "",
        "| 模块 | 已启用 | 规则数 | 检查轮次 | 最近测试 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, module in status["modules"].items():
        tests = module["tests"]
        summary = (
            "; ".join(
                f"{db}：{'当前' if suite['current'] else '过期'}，"
                f"通过 {suite['counts']['passed']}，"
                f"失败 {suite['counts']['failed']}，跳过 {suite['counts']['skipped']}；"
                f"该轮检查{'通过' if suite['checks_passed'] else '失败'}"
                for db, suite in tests["latest"].items()
            )
            or "未记录"
        )
        lines.append(
            f"| {name} | {'是' if module['enabled'] else '否'} | {len(module['rules'])} | "
            f"{tests['rounds']} | {cell(summary)} |"
        )
    lines += missing_packages(status)
    if status["runtime"] is not None:
        lines += runtime_summary(status["runtime"])
    return "\n".join(lines) + "\n"


def check_summary(recent: dict[str, Any] | None) -> list[str]:
    if recent is None:
        return []
    failed = "、".join(name for name, passed in recent["checks"].items() if not passed)
    return [
        f"最近一轮检查：{cell(recent['finished_at'])}；"
        f"{'通过' if recent['passed'] else '失败'}。"
        + (f"失败项目：{cell(failed)}。" if failed else "")
        + ("检查期间源码发生变化，结果过期。" if recent["source_changed"] else ""),
        "",
    ]


def missing_packages(status: dict[str, Any]) -> list[str]:
    lines = []
    for line in status["lines"]:
        for package in line["packages"]:
            if package["missing"]:
                lines += [
                    "",
                    f"{cell(line['name'])} / {cell(package['title'])} 尚未登记："
                    f"{', '.join(package['missing'])}",
                ]
    return lines


def module_markdown(module: dict[str, Any]) -> str:
    lines = [
        f"# {cell(module['title'])}（{module['name']}）",
        "",
        f"源码：{module['code']}；待确认规则 {len(module['pending'])} 项。",
        "",
    ]
    for database, suite in module["tests"]["latest"].items():
        lines += [
            f"最近 {database} 测试：{suite['finished_at']}；"
            f"{'适用于当前代码' if suite['current'] else '代码已改变，结果过期'}；"
            f"测试返回值 {suite['exit_code']}；"
            f"该轮检查{'通过' if suite['checks_passed'] else '失败'}。",
            "",
        ]
    for operation in module["operations"]:
        lines += operation_markdown(operation)
    if module.get("runtime") is not None:
        lines += runtime_summary(module["runtime"])
        for run in module["runtime"]["runs"]:
            lines += [
                "",
                f"## 运行 {cell(run['id'])}：{cell(run['operation'])}（{cell(run['status'])}）",
                "",
                "```mermaid",
                run["graph"],
                "```",
            ]
    return "\n".join(lines) + "\n"


def operation_markdown(operation: dict[str, Any]) -> list[str]:
    lines = [
        f"## {cell(operation['title'])}（{operation['name']}）",
        "",
        "```mermaid",
        operation["test_graph"] or operation["graph"],
        "```",
        "",
    ]
    if operation["last_test_run"]:
        lines += [
            "图中测试状态来自同一次运行，"
            f"结果 {cell(operation['last_test_run']['status'])}；其他测试执行次数见表。",
            "",
        ]
    lines += [
        "| 步骤 / 函数 | 条件 | 规则 | 源码 | 当前测试执行状态 | 最近耗时 | 最近产出 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for step in operation["steps"]:
        recent = step["last_test"] or {}
        elapsed = recent.get("elapsed_ms")
        output = recent.get("outputs", {}) if recent.get("outputs_recorded") else "未知"
        values = [
            f"{step['title']} / {step['name']}",
            step["condition"] or "总是执行",
            step["rule"],
            step["source"],
            step["test_executions"] or "未记录",
            f"{elapsed:.2f} ms" if elapsed is not None else "未知",
            output,
        ]
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    return lines


def runtime_summary(runtime: dict[str, Any]) -> list[str]:
    if not runtime["available"]:
        return ["", cell(runtime["reason"])]
    ratio = runtime.get("sample_ratio")
    text = f"{ratio:.1%}" if ratio is not None else "未知（没有计划）"
    return [
        "",
        f"数据库运行记录：最近 {len(runtime['runs'])} 条；"
        f"当前源码成功经过的计划操作 {len(runtime.get('planned_successful', []))} 个，"
        f"近期样例覆盖 {text}。",
        "历史版本的成功记录单独保留，不计入当前源码；这项比例不代表全部业务已经验收。",
    ]
