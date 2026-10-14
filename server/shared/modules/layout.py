"""
检查脚本生成的业务包结构。文件位置固定，步骤、纯计算和存储文件可以按用途增加，不能另建业务目录。
module.json 标明包采用的结构版本；它用于发现误建文件，不是限制开发者文件权限的安全机制。
"""

import json
from collections.abc import Iterable
from pathlib import Path

REQUIRED = {"README.md", "data.py", "public.py", "flow.py", "module.py"}
AREAS = {"steps", "store", "calc", "prompts"}
IGNORED = {"__pycache__", ".DS_Store"}


# 切换分支可留下字节码缓存；独立空目录仍属于误建的业务目录。
def actual_files(folder: Path) -> bool:
    entries = list(folder.rglob("*"))
    if not entries:
        return True
    for path in entries:
        if any(part in IGNORED for part in path.relative_to(folder).parts):
            continue
        if path.is_symlink() or path.is_file() or not any(path.iterdir()):
            return True
    return False


# 生成器与旧项目采用命令使用同一份结构说明，不能自定义允许的文件范围。
def descriptor(name: str, *, strict: bool = False) -> dict[str, object]:
    return {
        "schema_version": 1,
        "layout": "standard",
        "module": name,
        **({"dependencies": "strict"} if strict else {}),
    }


# 同时检查所有登记模块与目录，关闭模块也不能留下结构违规。
def check_layout(root: Path, names: Iterable[str], *, markers: bool = True) -> list[str]:
    service = root / "service"
    listed = set(names)
    problems = []
    for path in sorted(service.iterdir()):
        if path.name in IGNORED or path.name in {"README.md", "__init__.py"}:
            continue
        if path.is_dir() and not path.is_symlink() and not actual_files(path):
            continue
        if path.is_symlink() or not path.is_dir() or path.name not in listed:
            problems.append(f"service/{path.name}：不属于已登记的标准业务包")
    for name in sorted(listed):
        folder = service / name
        if not folder.is_dir() or folder.is_symlink():
            problems.append(f"service/{name}：找不到业务包目录")
            continue
        problems += check_package(folder, markers=markers)
    return problems


# 包根只接受固定文件和 data_主题.py；其他 Python 文件只能放在 steps、calc 或 store 中。
def check_package(folder: Path, *, markers: bool) -> list[str]:
    problems = [
        f"service/{folder.name}/{name}：缺少标准文件"
        for name in sorted(REQUIRED)
        if not (folder / name).is_file()
    ]
    for area in ("steps", "store"):
        for name in (
            ("README.md",)
            if area == "steps"
            else ("README.md", "contract.py", "sql.py", "tables.py")
        ):
            if not (folder / area / name).is_file():
                problems.append(f"service/{folder.name}/{area}/{name}：缺少标准文件")
    for path in sorted(folder.rglob("*")):
        parts = path.relative_to(folder).parts
        if any(part in IGNORED for part in parts):
            continue
        if path.is_symlink() or not permitted(parts, path.is_dir()):
            problems.append(f"service/{folder.name}/{'/'.join(parts)}：文件位置不符合标准结构")
    if markers:
        problems += check_marker(folder)
    return problems


# 步骤、纯计算和存储只允许一层命名文件，提示词接受文本和 Markdown，不允许可执行代码。
def permitted(parts: tuple[str, ...], directory: bool) -> bool:
    if len(parts) == 1:
        if directory:
            return parts[0] in AREAS
        name = parts[0]
        return name in REQUIRED | {"module.json", "__init__.py"} or (
            name.startswith("data_") and name.endswith(".py")
        )
    if len(parts) != 2 or directory or parts[0] not in AREAS:
        return False
    suffix = Path(parts[1]).suffix
    return suffix in ({".md", ".txt"} if parts[0] == "prompts" else {".py", ".md"})


# 缺少说明或擅自改变结构版本时拒绝启动，旧模块需要明确采用标准结构。
def check_marker(folder: Path) -> list[str]:
    path = folder / "module.json"
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [
            f"service/{folder.name}/module.json：缺少有效的结构说明；"
            "新包用 uv run dev new-module，旧包用 uv run dev adopt-modules"
        ]
    kind = content.get("kind") if isinstance(content, dict) else None
    normalized = (
        {key: value for key, value in content.items() if key != "kind"}
        if isinstance(content, dict)
        else content
    )
    if kind not in (None, "capability", "workflow") or normalized not in (
        descriptor(folder.name),
        descriptor(folder.name, strict=True),
    ):
        return [f"service/{folder.name}/module.json：结构说明与标准业务包不一致"]
    return []
