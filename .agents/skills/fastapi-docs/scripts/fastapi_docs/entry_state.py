"""
AGENTS当前状态由登记生成，每模块一行；具体操作通过模块/操作摘要深入。
"""

from pathlib import Path

from fastapi_project.development.ledger_sections import manual_text

from shared.modules.catalog import Catalog

BEGIN = "<!-- fastapi-current-state:begin -->"
END = "<!-- fastapi-current-state:end -->"


# 最近变更取已提交的业务变化记录；没有记录时说明情况，不依赖变化的Git时间。
def recent_change(project: Path, module: str) -> str:
    path = project / "doc" / module / "changes.md"
    try:
        lines = manual_text(path.read_text(), "changes").splitlines()
    except OSError:
        return "还没有手写业务变化记录"
    return next(
        (line.removeprefix("## ").strip()[:100] for line in lines if line.startswith("## ")),
        "还没有手写业务变化记录",
    )


# 声明提供职责、公开操作数量、计划/流程及关闭情况，不等同业务验收。
def block(catalog: Catalog, project: Path, disabled: set[str]) -> str:
    lines = [
        BEGIN,
        "## 当前状态（登记生成）",
        "",
        "下面是系统里登记了哪些模块。登记只说明代码里有了它，不代表业务已经完成；",
        "实际运行情况看业务现状档案，或用 project --summary 查询。",
        "",
    ]
    for module in catalog.modules.values():
        count = sum(item.entry for item in module.provides)
        state = "已关闭" if module.name in disabled else "启用"
        lines.append(
            f"- **{module.title}**（{module.name}）：对外 {count} 个操作、"
            f"{len(module.schedules)} 个定时入口、{len(module.pipelines)} 个多阶段流程；{state}。"
            f"最近一次业务改动：{recent_change(project, module.name)}。"
            f"运行情况见 `.agents/records/business-state/{module.name}.md`。"
        )
    if not catalog.modules:
        lines.append("- 当前还没有业务模块。新建模块后，这里会自动出现它的登记情况。")
    for name in sorted(disabled - catalog.modules.keys()):
        lines.append(f"- {name}：配置为关闭，当前没有登记，职责和操作未知。")
    lines += [
        "",
        "想看细节：project --module 模块名 --summary；project --operation 完整操作名。",
        END,
    ]
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
