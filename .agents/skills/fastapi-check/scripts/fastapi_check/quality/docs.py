"""
检查业务文档：每个模块在 doc/ 下有需求、规则、变化记录；长度不超过上限；
代码中引用的规则编号必须在 rules.md 中有对应标题；自动生成的 flows.md 必须与当前声明一致。
文风检查保证写给人看的文字符合约定：不用禁用词，不残留未翻译的英文。
"""

import os
import re
from pathlib import Path

from fastapi_check.quality.report import Problem
from fastapi_check.quality.rules import BUSINESS_DOCS, MAX_BUSINESS_DOC_LINES, PROJECT
from fastapi_docs.export_docs import outdated

from shared.data.fields import notes_of
from shared.modules.catalog import Catalog

# 文风硬规则：这些词在写给人看的文档里不该出现。约定见 fastapi-docs 的 writing-style.md。
BANNED_WORDS = ("阻断", "巡检", "巡查", "红线", "门禁", "判官", "————", "「", "」")
BANNED_PHRASES = ("Successful Response", "Validation Error")
# 约定文件自身要引用这些词；生成文件由“生成文档是否过期”间接保证合规。
STYLE_SKIP = ("writing-style.md",)
# 生成文件与模板块不检查：它们的内容由生成器版本决定；out/var 是测试和本机产物。
STYLE_GENERATED = (
    "doc/api/",
    "doc/modules.md",
    "doc/development.md",
    "doc/progress.md",
    "server/out/",
    "server/var/",
)


# 检查全部模块的业务文档。
def check_business_docs(catalog: Catalog, project: Path = PROJECT) -> list[Problem]:

    problems = check_development_rules(catalog, project)
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
                "运行 uv run python ../.agents/skills/fastapi-docs/scripts/run_docs.py export_docs",
            )
        )
    return problems


# 规则、词义与模拟身份分别核对，交付条件不能由运行成功推定。
def check_development_rules(
    catalog: Catalog, project: Path, *, delivery: bool | None = None
) -> list[Problem]:
    from fastapi_project.development.confirmed_cases import case_problems
    from fastapi_project.development.glossary import target_problems
    from fastapi_project.development.ledger import read_ledger

    delivery = os.environ.get("APP_DEVELOPMENT_DELIVERY") == "1" if delivery is None else delivery
    problems = [
        Problem("doc/rules-ledger.json", 0, "confirmed_case", problem)
        for problem in case_problems(
            project,
            read_ledger(project),
            delivery=delivery,
        )
    ]
    problems += [
        Problem("doc/glossary.json", 0, "glossary_target", problem)
        for problem in target_problems(project, catalog)
    ]
    if delivery:
        problems += [
            Problem(
                "service/" + binding.module.name,
                0,
                "simulated_implementation",
                "交付不能包含模拟骨架：" + binding.contract.name,
            )
            for binding in catalog.bindings.values()
            if any(part.simulated for part in binding.flow.steps)
        ]
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
                    name,
                    0,
                    "doc_missing",
                    "缺少业务文档",
                    "新模块用 fastapi_module.new_module 生成文档骨架",
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


# 检查写给人看的 Markdown 是否符合文风约定：禁用词和未翻译的英文残留。
# 检查范围是随源码提交的文档（业务文档、README、AGENTS.md、项目 Skill），
# 不检查生成文件和本机记录。
def check_writing_style(project: Path = PROJECT) -> list[Problem]:
    problems: list[Problem] = []
    folders = [project / "doc", project / ".agents" / "skills", project / "server"]
    singles = [project / "AGENTS.md", project / "README.md"]
    for path in singles + [item for folder in folders for item in folder.rglob("*.md")]:
        if not path.exists() or path.name in STYLE_SKIP:
            continue
        relative = path.relative_to(project).as_posix()
        if any(relative.startswith(prefix) for prefix in STYLE_GENERATED):
            continue
        if "/.agents/records/" in f"/{relative}":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for word in BANNED_WORDS + BANNED_PHRASES:
                if word in line:
                    problems.append(
                        Problem(
                            relative,
                            number,
                            "writing_style",
                            f"出现了禁用词 {word}",
                            "按文风与术语约定换成人能直接读懂的写法（fastapi-docs/references/writing-style.md）",
                        )
                    )
    return problems
