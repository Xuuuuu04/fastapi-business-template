"""
检查业务文档：每个模块在 doc/ 下有需求、规则、变化记录；长度不超过上限；
代码中引用的规则编号必须在 rules.md 中有对应标题；自动生成的 flows.md 必须与当前声明一致。
"""

import re
from pathlib import Path

from shared.data.fields import notes_of
from shared.modules.catalog import Catalog
from tools.export_docs import outdated
from tools.quality.report import Problem
from tools.quality.rules import BUSINESS_DOCS, MAX_BUSINESS_DOC_LINES, PROJECT


# 检查全部模块的业务文档。
def check_business_docs(catalog: Catalog, project: Path = PROJECT) -> list[Problem]:
    problems = []
    index = project / "doc" / "README.md"
    index_text = index.read_text(encoding="utf-8") if index.exists() else ""
    for name, module in catalog.modules.items():
        folder = project / module.doc
        problems += check_files(folder, project)
        if name not in index_text:
            problems.append(
                Problem("doc/README.md", 0, "doc_index", f"业务文档目录没有列出模块 {name}")
            )
        rules = folder / "rules.md"
        if rules.exists():
            problems += check_rule_ids(catalog, name, rules, project)
    for path in outdated(catalog):
        problems.append(
            Problem(
                path.relative_to(project).as_posix(),
                0,
                "doc_generated",
                "自动生成的文档与当前声明不一致",
                "运行 uv run python -m tools.export_docs",
            )
        )
    return problems


# 检查一个模块的三份业务文档是否存在、长度是否超限。
def check_files(folder: Path, project: Path) -> list[Problem]:
    problems = []
    for file_name in BUSINESS_DOCS:
        path = folder / file_name
        name = path.relative_to(project).as_posix()
        if not path.exists():
            problems.append(
                Problem(
                    name, 0, "doc_missing", "缺少业务文档", "新模块用 tools.new_module 生成文档骨架"
                )
            )
            continue
        count = len(path.read_text(encoding="utf-8").splitlines())
        if count > MAX_BUSINESS_DOC_LINES:
            problems.append(
                Problem(
                    name,
                    0,
                    "doc_lines",
                    f"文档有 {count} 行，超过 {MAX_BUSINESS_DOC_LINES} 行",
                    "按业务主题拆分或整理，保留全部业务条件和确认样例",
                )
            )
    return problems


# 检查代码中引用的规则编号都在 rules.md 中有标题。
def check_rule_ids(catalog: Catalog, name: str, rules: Path, project: Path) -> list[Problem]:
    text = rules.read_text(encoding="utf-8")
    written = set(re.findall(r"^#{2,4}\s+(R-\d+)\b", text, re.MULTILINE))
    used = rule_ids(catalog, name)
    path = rules.relative_to(project).as_posix()
    return [
        Problem(
            path,
            0,
            "rule_missing",
            f"代码引用了规则 {rule}，但文档中没有这一条",
            f"加一个标题“### {rule} 规则名称”",
        )
        for rule in sorted(used - written)
    ]


# 收集一个模块代码中引用的全部规则编号。
def rule_ids(catalog: Catalog, name: str) -> set[str]:
    found = set()
    for item, flow in catalog.modules[name].provides.items():
        found |= {part.rule for part in flow.steps if part.rule}
        for model in (flow.work, item.input, item.output):
            found |= {note.rule for note in notes_of(model).values() if note.rule}
    return found
