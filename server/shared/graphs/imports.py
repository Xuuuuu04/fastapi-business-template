"""
运行图的导入对账节点，只展示本次已执行的对账状态。
"""

import json

from shared.graphs.mermaid import label
from shared.modules.catalog import Binding
from shared.records.models import RunRecord


# 未执行对账时不画成功节点，运行入口仍明确显示未知。
def import_node(run: RunRecord, previous: str) -> list[str]:
    if not run.import_report or run.import_report.get("status") == "未知":
        return []
    state = run.import_report.get("status", "未知")
    text = label(f"导入对账：{state}")
    style = "ok" if state == "通过" else "failed"
    return [
        f'        reconcile_{run.id}["{text}"]:::{style}',
        f"        {previous} --> reconcile_{run.id}",
    ]


# 对账明细与图节点共同维护，正文不包含实际导入数据。
def report_header(run: RunRecord, is_root: bool) -> list[str]:
    heading = "## 步骤" if is_root else f"## 下一层：{run.title}（{run.id}）"
    lines = [heading, ""]
    if run.import_report:
        text = json.dumps(run.import_report, ensure_ascii=False).replace("|", "\\|")
        lines += ["导入对账：" + text, ""]
    return lines


# 对账节点来自任务声明，接在最后一个计算步骤与结果之间。
def import_plan_lines(binding: Binding, previous: str) -> tuple[list[str], str]:
    plan = next((j for j in binding.module.jobs if j.contract is binding.contract), None)
    if plan is None or plan.import_plan is None:
        return [], previous
    spec = plan.import_plan
    text = label(f"最后一批提交前对账：{spec.source_revision} / {spec.key}；行数、合计、质量、引用")
    return [f'    reconcile["{text}"]', f"    {previous} --> reconcile"], "reconcile"
