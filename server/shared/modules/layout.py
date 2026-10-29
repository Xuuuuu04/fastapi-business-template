import json
from collections.abc import Iterable
from pathlib import Path

REQUIRED = {"README.md", "data.py", "public.py", "flow.py", "module.py"}
AREAS = {"steps", "store", "calc", "prompts"}
IGNORED = {"__pycache__", ".DS_Store"}


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


KINDS = ("capability", "workflow")


def descriptor(name: str, *, kind: str = "") -> dict[str, object]:
    return {
        "schema_version": 1,
        "layout": "standard",
        "module": name,
        **({"kind": kind} if kind else {}),
        "dependencies": "strict",
    }


def declared_kind(folder: Path) -> str | None:
    try:
        content = json.loads((folder / "module.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    kind = content.get("kind") if isinstance(content, dict) else None
    return kind if kind in KINDS else None


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


def check_package(folder: Path, *, markers: bool) -> list[str]:
    problems = [
        f"service/{folder.name}/{name}：缺少标准文件"
        for name in sorted(REQUIRED)
        if not (folder / name).is_file()
    ]
    kind = declared_kind(folder) if markers else None
    required = [("steps", "README.md")]
    if kind != "workflow":
        required += [
            ("store", name) for name in ("README.md", "contract.py", "sql.py", "tables.py")
        ]
    elif (folder / "store").exists():
        problems.append(f"service/{folder.name}/store：流程包不拥有数据，数据存取放到能力包")
    for area, name in required:
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


def permitted(parts: tuple[str, ...], directory: bool) -> bool:
    if len(parts) == 1:
        if directory:
            return parts[0] in AREAS
        name = parts[0]
        return name in REQUIRED | {"module.json", "__init__.py"} or (
            name.startswith(("data_", "flow_")) and name.endswith(".py")
        )
    if len(parts) != 2 or directory or parts[0] not in AREAS:
        return False
    suffix = Path(parts[1]).suffix
    return suffix in ({".md", ".txt"} if parts[0] == "prompts" else {".py", ".md"})


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
    if kind not in KINDS:
        kinds = "capability（能力包）或 workflow（流程包）"
        return [f"service/{folder.name}/module.json：kind 必须写 {kinds}"]
    if normalized != descriptor(folder.name):
        return [f"service/{folder.name}/module.json：结构说明与标准业务包不一致"]
    return []
