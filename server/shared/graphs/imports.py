import json

from shared.graphs.mermaid import label
from shared.modules.catalog import Binding
from shared.records.models import RunRecord


def import_node(run: RunRecord, previous: str) -> list[str]:
    if not run.import_report or run.import_report.get("status") == "未知":
        return []
    state = run.import_report.get("status", "未知")
    text = label(f"导入结果核对：{state}")
    style = "ok" if state == "通过" else "failed"
    return [
        f'        reconcile_{run.id}["{text}"]:::{style}',
        f"        {previous} --> reconcile_{run.id}",
    ]


def report_header(run: RunRecord, is_root: bool) -> list[str]:
    heading = "## 步骤" if is_root else f"## 调用的操作：{run.title}（{run.id}）"
    lines = [heading, ""]
    if run.import_report:
        text = json.dumps(run.import_report, ensure_ascii=False).replace("|", "\\|")
        lines += ["导入结果核对：" + text, ""]
    return lines


def import_plan_lines(binding: Binding, previous: str) -> tuple[list[str], str]:
    plan = next((j for j in binding.module.jobs if j.contract is binding.contract), None)
    if plan is None or plan.import_plan is None:
        return [], previous
    spec = plan.import_plan
    text = label(
        f"最后一批提交前核对：{spec.source_revision} / {spec.key}；"
        "核对行数、合计值、数据要求和引用关系"
    )
    return [f'    reconcile["{text}"]', f"    {previous} --> reconcile"], "reconcile"
