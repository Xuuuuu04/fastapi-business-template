"""
AGENTS当前状态由登记生成，每模块一行；具体操作通过模块/操作摘要深入。
"""

from pathlib import Path

from shared.modules.catalog import Catalog

BEGIN = "<!-- fastapi-current-state:begin -->"
END = "<!-- fastapi-current-state:end -->"


# 最近变更取已提交的业务变化记录；没有记录时未知，不依赖变化的Git时间。
def recent_change(project: Path, module: str) -> str:
    path = project / "doc" / module / "changes.md"
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return "未知：缺少变化记录"
    return next(
        (line.removeprefix("## ").strip()[:100] for line in lines if line.startswith("## ")),
        "未知：尚无变化条目",
    )


# 声明提供职责、公开操作数量、计划/流程及关闭情况，不等同业务验收。
def block(catalog: Catalog, project: Path, disabled: set[str]) -> str:
    lines = [
        BEGIN,
        "## 当前状态（登记生成）",
        "",
        "登记不等于业务完成；运行状态见业务现状或project --summary。",
        "",
    ]
    for module in catalog.modules.values():
        count = sum(item.entry for item in module.provides)
        state = "已关闭" if module.name in disabled else "启用"
        lines.append(
            f"- {module.name}：{module.title}；公开操作{count}；定时{len(module.schedules)}；"
            f"流程{len(module.pipelines)}；{state}；"
            f"最近改动：{recent_change(project, module.name)}。"
        )
    if not catalog.modules:
        lines.append("- 当前没有业务模块、业务操作、定时计划或业务流程。")
    for name in sorted(disabled - catalog.modules.keys()):
        lines.append(f"- {name}：配置为关闭，当前未登记，职责和操作未知。")
    lines += ["", "深入：project --module 模块名 --summary；project --operation 完整操作名。", END]
    return "\n".join(lines)


# 只替换生成区域，产品长期说明和手写判断完整保留。
def render(catalog: Catalog, project: Path, disabled: set[str]) -> str:
    path = project / "AGENTS.md"
    text = path.read_text() if path.exists() else "# 项目入口\n"
    generated = block(catalog, project, disabled)
    if BEGIN in text and END in text:
        first = text.index(BEGIN)
        last = text.index(END, first) + len(END)
        return text[:first] + generated + text[last:]
    return text.rstrip() + "\n\n" + generated + "\n"


# check只比较，缺少生成段或内容变化都指出入口文件。
def stale(catalog: Catalog, project: Path, disabled: set[str]) -> bool:
    path = project / "AGENTS.md"
    return not path.exists() or path.read_text() != render(catalog, project, disabled)
