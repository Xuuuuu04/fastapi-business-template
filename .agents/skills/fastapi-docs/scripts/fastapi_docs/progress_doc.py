import re
from dataclasses import dataclass
from pathlib import Path

from shared.modules.catalog import Catalog

RULE_HEADING = re.compile(r"^#{2,4}\s+(R-\d+)\s*(.*)$")
RULE_ID = re.compile(r"\bR-\d+\b")
PENDING = "待确认"
MAX_EXCERPT = 80
HEADER = "> 本文件由 `uv run dev docs` 根据业务文档、测试和任务清单生成，不要手工修改。"


@dataclass(frozen=True)
class Pending:
    module: str
    place: str
    rule: str
    text: str


def rules_of(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = RULE_HEADING.match(line)
        if match:
            found[match.group(1)] = match.group(2).strip()
    return found


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


def excerpt(line: str) -> str:
    text = line.strip().lstrip("#-| ").strip()
    start = max(text.find(PENDING) - MAX_EXCERPT // 2, 0)
    part = text[start : start + MAX_EXCERPT]
    return ("…" if start else "") + part + ("…" if start + MAX_EXCERPT < len(text) else "")


def tested_rules(project: Path, module: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for kind in ("modules", "integration"):
        folder = project / "server" / "tests" / kind / module
        for path in sorted(folder.rglob("*.py")) if folder.exists() else []:
            for rule in sorted(set(RULE_ID.findall(path.read_text(encoding="utf-8")))):
                found.setdefault(rule, []).append(path.relative_to(project / "server").as_posix())
    return found


def task_counts(project: Path) -> tuple[int, int]:
    path = project / "doc" / "tasks.md"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return len(re.findall(r"^\s*- \[ \]", text, re.M)), len(re.findall(r"^\s*- \[x\]", text, re.M))


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


def pending_lines(pending: list[Pending]) -> list[str]:
    lines = ["", "## 待确认的业务问题", ""]
    lines += [
        "下面这些业务问题需要人来决定。确认之后，把对应的规则改写清楚、"
        "删掉“待确认”字样，并在 changes.md 里记录这次变化。",
        "",
    ]
    if not pending:
        return [*lines, "目前没有待确认的问题。"]
    rows = [f"| {one.module} | {one.rule} | {cell(one.text)} | {one.place} |" for one in pending]
    return [*lines, "| 模块 | 规则 | 内容 | 位置 |", "| --- | --- | --- | --- |", *rows]


def untested_lines(untested: list[str]) -> list[str]:
    lines = ["", "## 还没有测试标注的规则", ""]
    lines += [
        "一条规则要有测试，需要在测试的注释或说明里写上规则编号"
        "（例如“R-03：……”）。下面这些规则还没有找到对应的测试标注。",
        "",
    ]
    if not untested:
        return [*lines, "没有遗漏，每条规则都有测试标注。"]
    return [*lines, "| 模块 | 规则 | 标题 |", "| --- | --- | --- |", *untested]


def cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
