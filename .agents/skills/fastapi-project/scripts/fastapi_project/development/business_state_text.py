"""
业务现状生成部分的文字渲染：把登记与观察事实写成完整句子。
这里只做文字整理，不读写文件；数据结构见 business_state.py。
"""

import time
from typing import Any

from shared.records.models import RUN_STATUS_TEXT


# 把时间戳写成可读的本地时间；没有时间时如实说明。
def time_text(value: Any) -> str:
    if not value:
        return "未知（还没有连接数据库读取过）"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(value)))


# 一条运行观察（编号、状态、时间）写成一句话；查不到时如实说明。
def record_text(value: Any) -> str:
    if not isinstance(value, dict):
        return str(value)
    started = time_text(value.get("started_at") or value.get("created_at"))
    raw = str(value.get("status") or value.get("state") or "状态未知")
    status = RUN_STATUS_TEXT.get(raw, raw)
    return f"{value.get('contract') or value.get('pipeline')}：{status}（{started}）"


# 带数量的观察小结（逾期、待确认）：数量完整，例子最多三个，省略数写明。
def attention_text(value: Any, label: str) -> str:
    if not isinstance(value, dict):
        return str(value)
    count = value.get("count", 0)
    if not count:
        return f"没有{label}的记录"
    rows = value.get("examples", [])
    samples = "；".join(record_text(row) for row in rows[:3])
    more = f"（另有 {value.get('omitted', 0)} 条省略）" if value.get("omitted") else ""
    return f"有 {count} 条，例如：{samples}{more}"


# 最近运行的观察：顶层操作一句话，各流程各一句话。
def last_text(value: Any) -> str:
    if not isinstance(value, dict):
        return str(value)
    parts = []
    operation = value.get("operation")
    parts.append(
        record_text(operation)
        if isinstance(operation, dict)
        else f"顶层操作：{operation}（数据库里没有保留运行记录）"
    )
    for name, row in value.get("pipelines", {}).items():
        item = record_text(row) if isinstance(row, dict) else str(row)
        parts.append(f"流程 {name}：{item}")
    note = value.get("evidence")
    return "；".join(parts) + (f"。注意：{note}" if note else "")


# 定时入口写成一句话：什么入口、触发什么操作、什么节奏。
def schedule_text(item: dict[str, Any]) -> str:
    every = item.get("every_seconds")
    daily = item.get("daily_at")
    rhythm = f"每隔 {every:g} 秒" if every else f"每天 {daily}"
    zone = f"，{item['zone']}" if item.get("zone") else ""
    return f"{item['name']} → {item['operation']}（{rhythm}{zone}）"


# 后台任务一行：总数、分段数量和前几个名称，其余指明去向。
def jobs_text(declared: dict[str, Any]) -> str:
    jobs = declared["jobs"]
    segmented = sum(1 for item in jobs if item["segmented"])
    lead = f"共 {len(jobs)} 个" + (f"，其中分段任务 {segmented} 个：" if segmented else "：")
    return lead + preview([item["name"] for item in jobs])


# 继续查看的入口命令。
def footer_text(name: str) -> str:
    base = "`uv run dev status --module " + name
    return f"- **继续查看**：登记和测试情况用 {base} --summary`；真实运行记录用 {base} --runs`。"


# 一屏优先，长清单明确省略数量，完整操作通过 project 详情深入。
def preview(items: list[str], maximum: int = 8) -> str:
    if not items:
        return "无"
    result = "、".join(items[:maximum])
    return result + (
        f"（其余 {len(items) - maximum} 个用 uv run dev status --module 查看）"
        if len(items) > maximum
        else ""
    )
