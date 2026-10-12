"""
从规则账本生成规则状态和修订文档；历史手写规则保持兼容，不覆盖未采纳的业务文字。
"""

from pathlib import Path

from fastapi_project.development.ledger import read_ledger

STATES = {
    "inferred": "推定，待确认",
    "adopted": "采纳，待确认",
    "confirmed": "明确确认",
    "retired": "废止",
}


# 每个业务包的独立账本文档同时展示状态和变更来源，不把代码存在当作规则确认。
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
    return documents
