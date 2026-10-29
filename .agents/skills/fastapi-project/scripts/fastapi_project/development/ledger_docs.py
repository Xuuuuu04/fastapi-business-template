from pathlib import Path

from fastapi_project.development.ledger import read_ledger
from fastapi_project.development.ledger_models import RuleLedger
from fastapi_project.development.ledger_sections import cell, section

STATES = {
    "inferred": "推定，待确认",
    "adopted": "采纳，待确认",
    "confirmed": "明确确认",
    "retired": "废止",
}


def ledger_documents(project: Path) -> dict[Path, str]:
    ledger = read_ledger(project)
    modules = sorted({rule.id.split(".")[0] for rule in ledger.rules})
    documents = {}
    for module in modules:
        lines = [
            f"# {module}：规则账本",
            "",
            "这份文档由dev docs生成，原话摘要不验证确认者身份。",
            "",
        ]
        for rule in ledger.rules:
            if not rule.id.startswith(module + "."):
                continue
            lines += [
                f"## {rule.id}（修订{rule.revision}）",
                "",
                rule.text,
                "",
                f"状态：{STATES[rule.state]}；风险：{rule.risk}。",
                "",
                f"来源：{', '.join(rule.sources)}；"
                f"保护样例：{', '.join(rule.case_digests) or '未提供'}。",
                "",
            ]
        lines += ["## 修订历史", ""]
        for event in ledger.events:
            if event.rule.startswith(module + "."):
                lines += [f"- {event.rule} 修订{event.revision}：{event.action}；{event.reason}"]
        documents[project / "doc" / module / "ledger.md"] = "\n".join(lines) + "\n"
        documents.update(index_documents(project, module, ledger))
    return documents


def index_documents(project: Path, module: str, ledger: RuleLedger) -> dict[Path, str]:
    rules = [rule for rule in ledger.rules if rule.id.startswith(module + ".")]
    events = [event for event in ledger.events if event.rule.startswith(module + ".")]
    body = [
        "## 规则账本状态（生成）",
        "",
        "完整规则与修订见[规则账本](ledger.md)。段外历史文字不代表当前修订已确认。",
        "",
        "| 规则 | 修订 | 状态 | 风险 | 摘要 |",
        "| --- | --- | --- | --- | --- |",
    ]
    body += [
        f"| {rule.id} | {rule.revision} | {STATES[rule.state]} | {rule.risk} | {cell(rule.text)} |"
        for rule in rules
    ]
    changes = ["## 账本修订（生成）", "", "修订不等于部署或业务验收。", ""]
    changes += [
        f"- {event.rule} 修订{event.revision}：{cell(event.action)}；{cell(event.reason)}"
        for event in events
    ]
    folder = project / "doc" / module
    return {
        folder / "rules.md": section(folder / "rules.md", "rules", "\n".join(body)),
        folder / "changes.md": section(folder / "changes.md", "changes", "\n".join(changes)),
    }
