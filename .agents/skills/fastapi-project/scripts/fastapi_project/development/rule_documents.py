import json
import re
from pathlib import Path

from fastapi_project.development.ledger import add_source, propose, read_ledger, transition
from fastapi_project.development.ledger_lock import serialized
from fastapi_project.development.ledger_models import LedgerRule, RuleSource
from fastapi_project.development.ledger_sections import manual_text


def confirm_sheet(project: Path) -> str:
    ledger = read_ledger(project)
    ranks = {"high": 0, "medium": 1, "low": 2}
    lines = ["# 规则确认单", "", "确认声明需要引用原话；检查通过不能替代确认。", ""]
    for rule in sorted(ledger.rules, key=lambda rule: (ranks[rule.risk], rule.id)):
        if rule.state in {"confirmed", "retired"}:
            continue
        lines += [f"## {rule.id}：{rule.risk}", "", rule.text, ""]
        module = rule.id.split(".")[0]
        cases = []
        for path in sorted((project / "doc" / module / "cases").glob("*.json")):
            data = json.loads(path.read_text())
            if data["id"].rsplit("-C", 1)[0] == rule.id:
                cases.append(data)
        for case in cases[:4]:
            lines.append(f"- {case['id']}：输入 {case['input']}；预期 {case['expected']}")
        if not cases:
            lines.append("样例未提供，需要补充后确认。")
        lines.append("")
    return "\n".join(lines)


@serialized
def adopt_markdown(project: Path, module: str) -> list[str]:
    rules = markdown_rules(project, module)
    source = f"markdown-{module}"
    ledger = read_ledger(project)
    existing = {item.id for item in ledger.rules}
    if any(rule.id in existing for rule in rules):
        raise ValueError("规则已经存在，历史导入不能覆盖当前修订")
    add_source(
        project,
        RuleSource(
            id=source,
            kind="document",
            summary="历史规则文档，未确认原话",
            locator=f"doc/{module}/rules.md",
        ),
    )
    for rule in rules:
        propose(project, rule, reason="采集历史规则文本，保留原文待确认")
        transition(project, rule.id, "adopted", reason="采纳历史文档，尚未人类确认")
    return [rule.id for rule in rules]


def markdown_rules(project: Path, module: str) -> list[LedgerRule]:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", module):
        raise ValueError("业务包名称不合法")
    text = manual_text((project / "doc" / module / "rules.md").read_text(), "rules")
    sections = list(re.finditer(r"^#{2,4}\s+(R-\d+)\s+(.+)$", text, re.MULTILINE))
    if not sections:
        raise ValueError("规则文档没有可解析的规则标题，请保留原件并先整理")
    rules = []
    for index, heading in enumerate(sections):
        end = sections[index + 1].start() if index + 1 < len(sections) else len(text)
        rules.append(
            LedgerRule(
                id=f"{module}.{heading.group(1)}",
                text=text[heading.end() : end].strip() or heading.group(2),
                sources=[f"markdown-{module}"],
            )
        )
    if len({rule.id for rule in rules}) != len(rules):
        raise ValueError("历史规则编号重复")
    return rules


def supersede(project: Path, identity: str, text: str, source: str, reason: str) -> LedgerRule:
    ledger = read_ledger(project)
    previous = next(rule for rule in ledger.rules if rule.id == identity)
    material = next(item for item in ledger.sources if item.id == source)
    if previous.state == "confirmed" and (
        material.kind != "user_quote" or source in previous.sources
    ):
        raise ValueError("修订已确认规则需要新的原话来源")
    return propose(
        project, previous.model_copy(update={"text": text, "sources": [source]}), reason=reason
    )
