from shared.db.budget import budget_text
from shared.records.models import RUN_STATUS_TEXT, WRITES_TEXT, RunRecord, StepRecord
from shared.records.segments import segment_text


def summarize(run: RunRecord) -> str:
    if run.status == "refused":
        return f"“{run.title}”没有执行：{run.error_message}。"
    if run.status in ("running", "lost"):
        return running_text(run)
    parts = [finished_text(run) if run.status == "ok" else failed_text(run)]
    notes = note_text(run.steps)
    if notes:
        parts.append(notes)
    parts.append(f"{WRITES_TEXT.get(run.writes, run.writes)}。")
    if run.segment_number:
        parts.append(segment_text(run).strip(" ·") + "。")
    if run.segment_warning:
        parts.append("提醒：" + run.segment_warning + "。")
    if (
        run.status == "ok"
        and run.query_budget
        and (run.query_budget["exceeded"] or run.query_budget["repeated"])
    ):
        parts.append(budget_text(run.query_budget))
    if run.gaps:
        parts.append("记录不完整：" + "；".join(run.gaps) + "。")
    return "".join(parts)


def finished_text(run: RunRecord) -> str:
    done = [step for step in run.steps if step.status == "ok"]
    skipped = [step for step in run.steps if step.status == "skipped"]
    text = f"“{run.title}”已完成，执行 {len(done)} 个步骤，用时 {duration(run.elapsed_ms)}。"
    if skipped:
        names = "、".join(f"“{step.title}”" for step in skipped)
        text += f"条件不满足而跳过：{names}。"
    return text


def failed_text(run: RunRecord) -> str:
    failed = next((step for step in run.steps if step.status == "failed"), None)
    if failed is None:
        return f"“{run.title}”失败：{run.error_message}。"
    text = f"“{run.title}”在“{failed.title}”步骤停止：{run.error_message}。"
    if failed.children:
        text += "失败发生在这一步调用的其他操作中，可展开查看。"
    if failed.error_place:
        text += f"出错位置：{failed.error_place}。"
    finished = sum(step.status == "ok" for step in run.steps)
    remaining = not_started(run)
    text += f"此前已完成 {finished} 个步骤"
    text += f"，之后的 {remaining} 个步骤没有执行。" if remaining else "。"
    if run.error_kind == "broken":
        text += "这是代码与声明不一致的问题，需要修改代码。"
    return text


def running_text(run: RunRecord) -> str:
    current = next((step for step in reversed(run.steps) if step.status == "running"), None)
    state = RUN_STATUS_TEXT.get(run.status, run.status)
    where = f"，当前步骤“{current.title}”" if current else ""
    text = f"“{run.title}”{state}{where}，已用时 {duration(run.elapsed_ms)}。"
    return text + ("提醒：" + run.segment_warning + "。" if run.segment_warning else "")


def note_text(steps: list[StepRecord]) -> str:
    lines = [f"“{step.title}”：{'；'.join(step.notes)}" for step in steps if step.notes]
    return "数据说明：" + "；".join(lines) + "。" if lines else ""


def not_started(run: RunRecord) -> int:
    seen = {step.name for step in run.steps}
    return sum(name not in seen for name in run.planned)


def duration(elapsed_ms: float) -> str:
    if elapsed_ms < 1000:
        return f"{elapsed_ms:.0f} 毫秒"
    return f"{elapsed_ms / 1000:.1f} 秒"
