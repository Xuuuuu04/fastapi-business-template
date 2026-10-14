"""
AGENTS当前状态由登记生成，每模块一行；具体操作通过模块/操作摘要深入。
"""

from pathlib import Path

from fastapi_project.development.ledger_sections import manual_text

from shared.modules.catalog import Catalog

BEGIN = "<!-- fastapi-current-state:begin -->"
END = "<!-- fastapi-current-state:end -->"
MAX_ITEMS = 3


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
        "实际运行情况看业务现状档案，或用 uv run dev status --summary 查询。",
        "",
    ]
    modules = list(catalog.modules.values())
    unknown = sorted(disabled - catalog.modules.keys())
    for module in modules[:MAX_ITEMS]:
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
    for name in unknown[: max(0, MAX_ITEMS - len(modules))]:
        lines.append(f"- {name}：配置为关闭，当前没有登记，职责和操作未知。")
    omitted = max(0, len(modules) + len(unknown) - MAX_ITEMS)
    if omitted:
        lines.append(f"- 另有 {omitted} 个登记项；完整清单用 `uv run dev status --summary` 查看。")
    lines += [
        "",
        "想看细节：uv run dev status --module 模块名 --summary；"
        "uv run dev status --operation 完整操作名。",
        END,
    ]
    return "\n".join(lines)


# 只替换生成区域，产品长期说明和手写判断完整保留。
def render(catalog: Catalog, project: Path, disabled: set[str]) -> str:
    path = project / "AGENTS.md"
    text = path.read_text() if path.exists() else "# 项目入口\n"
    generated = block(catalog, project, disabled)
    if (BEGIN in text or END in text) and (
        text.count(BEGIN) != 1 or text.count(END) != 1 or text.index(END) < text.index(BEGIN)
    ):
        raise ValueError("AGENTS生成边界损坏，请先保留并修复原件")
    if BEGIN in text and END in text:
        first = text.index(BEGIN)
        last = text.index(END, first) + len(END)
        return text[:first] + generated + text[last:]
    return text.rstrip() + "\n\n" + generated + "\n"


# check只比较，缺少生成段或内容变化都指出入口文件。
def stale(catalog: Catalog, project: Path, disabled: set[str]) -> bool:
    path = project / "AGENTS.md"
    return not path.exists() or path.read_text() != render(catalog, project, disabled)
