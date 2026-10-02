"""
生成 doc/progress.md：人在开发过程中观察进度和质量的入口。内容全部从仓库中现有的文件统计，
每次改动后重新生成并提交，进度的变化就出现在提交差异里：
- 各模块的操作数、规则数、有测试标注的规则数、待确认条数；
- 全部“待确认”的业务问题及所在位置；
- 还没有测试标注的规则（测试注释或说明中写了规则编号，才算这条规则有测试）；
- 任务清单 doc/tasks.md 中未完成和已完成的条数。
"""

import re
from dataclasses import dataclass
from pathlib import Path

from shared.modules.catalog import Catalog

RULE_HEADING = re.compile(r"^#{2,4}\s+(R-\d+)\s*(.*)$")
RULE_ID = re.compile(r"\bR-\d+\b")
PENDING = "待确认"
MAX_EXCERPT = 80
HEADER = (
    "> 本文件由 `uv run python -m tools.export_docs` 根据业务文档、测试和任务清单生成，"
    "不要手工修改。"
)


# 业务文档中尚未确认的一项规则或问题，供开发进度汇总。
@dataclass(frozen=True)
class Pending:
    module: str
    place: str
    rule: str
    text: str


# 读取 rules.md 中的规则编号和标题。
def rules_of(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = RULE_HEADING.match(line)
        if match:
            found[match.group(1)] = match.group(2).strip()
    return found


# 找出一个模块业务文档中所有写了“待确认”的行，并记下所在的规则。
def pending_of(project: Path, module: str) -> list[Pending]:
    items = []
    for name in ("needs.md", "rules.md"):
        path = project / "doc" / module / name
        if not path.exists():
            continue
        rule = ""
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = RULE_HEADING.match(line)
            if match:
                rule = match.group(1)
            if PENDING in line and not line.lstrip().startswith(">"):
                place = f"doc/{module}/{name}:{number}"
                items.append(Pending(module, place, rule, excerpt(line)))
    return items


# 截取“待确认”附近的文字，便于在表格中阅读。
def excerpt(line: str) -> str:
    text = line.strip().lstrip("#-| ").strip()
    start = max(text.find(PENDING) - MAX_EXCERPT // 2, 0)
    part = text[start : start + MAX_EXCERPT]
    return ("…" if start else "") + part + ("…" if start + MAX_EXCERPT < len(text) else "")


# 统计一个模块的测试中标注过的规则编号，以及标注它的测试文件。
def tested_rules(project: Path, module: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for kind in ("modules", "integration"):
        folder = project / "server" / "tests" / kind / module
        for path in sorted(folder.rglob("*.py")) if folder.exists() else []:
            for rule in sorted(set(RULE_ID.findall(path.read_text(encoding="utf-8")))):
                found.setdefault(rule, []).append(path.relative_to(project / "server").as_posix())
    return found


# 统计任务清单中未完成和已完成的条数。
def task_counts(project: Path) -> tuple[int, int]:
    path = project / "doc" / "tasks.md"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return len(re.findall(r"^\s*- \[ \]", text, re.M)), len(re.findall(r"^\s*- \[x\]", text, re.M))


# 生成 doc/progress.md 全文。
def progress_doc(catalog: Catalog, project: Path) -> str:
    open_tasks, done_tasks = task_counts(project)
    lines = ["# 开发进度与质量", "", HEADER, ""]
    lines += [
        f"任务清单（[tasks.md](tasks.md)）：未完成 {open_tasks} 项，已完成 {done_tasks} 项。",
        "",
        "## 模块",
        "",
        "| 模块 | 名称 | 操作 | 规则 | 有测试标注的规则 | 待确认 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    pending: list[Pending] = []
    untested: list[str] = []
    for name, module in catalog.modules.items():
        rules = rules_of(project / "doc" / name / "rules.md")
        tested = tested_rules(project, name)
        waiting = pending_of(project, name)
        pending += waiting
        missing = [rule for rule in rules if rule not in tested]
        untested += [f"| {name} | {rule} | {cell(rules[rule])} |" for rule in missing]
        covered = f"{len(rules) - len(missing)}/{len(rules)}"
        values = [name, module.title, len(module.provides), len(rules), covered, len(waiting)]
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    return "\n".join(lines + pending_lines(pending) + untested_lines(untested)) + "\n"


# 待确认的业务问题一节。
def pending_lines(pending: list[Pending]) -> list[str]:
    lines = ["", "## 待确认的业务问题", ""]
    lines += ["需要人决定。确认后改写对应规则，删去“待确认”，并在 changes.md 记录。", ""]
    if not pending:
        return [*lines, "没有。"]
    rows = [f"| {one.module} | {one.rule} | {cell(one.text)} | {one.place} |" for one in pending]
    return [*lines, "| 模块 | 规则 | 内容 | 位置 |", "| --- | --- | --- | --- |", *rows]


# 还没有测试标注的规则一节。
def untested_lines(untested: list[str]) -> list[str]:
    lines = ["", "## 还没有测试标注的规则", ""]
    lines += ["测试的注释或说明中写上规则编号（例如“R-03：……”），这条规则才算有测试。", ""]
    if not untested:
        return [*lines, "没有，每条规则都有测试标注。"]
    return [*lines, "| 模块 | 规则 | 标题 |", "| --- | --- | --- |", *untested]


# 整理表格单元格。
def cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
