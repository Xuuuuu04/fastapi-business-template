"""
检查 README：每个含代码的目录都要有 README；长度不超过上限；
业务模块的 README 必须包含固定小节，并列出本模块的每个公开操作。
"""

from pathlib import Path

from fastapi_check.quality.report import Problem, files_under, relative
from fastapi_check.quality.rules import (
    MAX_MODULE_README_LINES,
    MAX_README_LINES,
    MODULE_README_SECTIONS,
    README_DIRS,
    ROOT,
)


# 检查全部 README；测试只要求 tests/ 和下一层分类目录有 README，按模块再分的目录不要求。
def check_readmes(
    root: Path = ROOT, contracts: dict[str, list[str]] | None = None
) -> list[Problem]:
    folders = {path.parent for path in files_under(root, README_DIRS, ".py")}
    folders = {folder for folder in folders if needs_readme(folder.relative_to(root).parts)}
    problems = []
    for folder in sorted(folders):
        readme = folder / "README.md"
        if not readme.exists():
            problems.append(
                Problem(
                    relative(folder, root),
                    0,
                    "readme_missing",
                    "目录缺少 README.md",
                    "说明这个目录负责什么、下一步该看哪里",
                )
            )
            continue
        problems += check_length(readme, root)
    for module_dir in sorted((root / "service").glob("*/")):
        if (module_dir / "module.py").exists():
            names = (contracts or {}).get(module_dir.name, [])
            problems += check_module_readme(module_dir / "README.md", names, root)
    return problems


# 判断目录是否需要 README。
def needs_readme(parts: tuple[str, ...]) -> bool:
    return not (parts[:1] == ("tests",) and len(parts) > 2)


# 检查 README 的行数。
def check_length(readme: Path, root: Path) -> list[Problem]:
    count = len(readme.read_text(encoding="utf-8").splitlines())
    limit = MAX_MODULE_README_LINES if readme.parent.parent.name == "service" else MAX_README_LINES
    if count <= limit:
        return []
    return [
        Problem(
            relative(readme, root),
            0,
            "readme_lines",
            f"README 有 {count} 行，超过 {limit} 行",
            "整理成要点；详细的业务规则放到 doc/ 下的业务文档，不删除业务条件和确认样例",
        )
    ]


# 检查业务模块 README 的固定小节和公开操作清单。
def check_module_readme(readme: Path, names: list[str], root: Path) -> list[Problem]:
    name = relative(readme, root)
    if not readme.exists():
        return []
    text = readme.read_text(encoding="utf-8")
    problems = [
        Problem(name, 0, "readme_section", f"缺少小节“{section}”")
        for section in MODULE_README_SECTIONS
        if section not in text
    ]
    problems += [
        Problem(
            name, 0, "readme_operation", f"没有写公开操作 {item}", "在“公开操作”小节列出它的用途"
        )
        for item in names
        if item not in text
    ]
    return problems
