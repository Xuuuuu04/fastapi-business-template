import json
from collections.abc import Iterable
from pathlib import Path

REQUIRED = {"data.py", "public.py", "flow.py", "module.py"}
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


def descriptor(name: str, kind: str) -> dict[str, object]:
    return {"schema_version": 1, "layout": "standard", "module": name, "kind": kind}


def declared_kind(folder: Path) -> str:
    return str(json.loads((folder / "module.json").read_text(encoding="utf-8"))["kind"])


def check_layout(root: Path, names: Iterable[str]) -> list[str]:
    service = root / "service"
    listed = set(names)
    problems = []
    for path in sorted(service.iterdir()) if service.is_dir() else []:
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
        problems += check_package(folder)
    return problems


def check_package(folder: Path) -> list[str]:
    problems = [
        f"service/{folder.name}/{name}：缺少标准文件"
        for name in sorted(REQUIRED)
        if not (folder / name).is_file()
    ]
    marker = check_marker(folder)
    if not marker:
        problems += kind_problems(folder, declared_kind(folder))
    for path in sorted(folder.rglob("*")):
        parts = path.relative_to(folder).parts
        if any(part in IGNORED for part in parts):
            continue
        if path.is_symlink() or not permitted(parts, path.is_dir()):
            problems.append(f"service/{folder.name}/{'/'.join(parts)}：文件位置不符合标准结构")
    return problems + marker


def kind_problems(folder: Path, kind: str) -> list[str]:
    if kind == "workflow":
        if (folder / "store").exists():
            return [f"service/{folder.name}/store：流程包不拥有数据，数据存取放到能力包"]
        return []
    return [
        f"service/{folder.name}/store/{name}：缺少标准文件"
        for name in ("contract.py", "sql.py", "tables.py")
        if not (folder / "store" / name).is_file()
    ]


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
    return suffix in ({".md", ".txt"} if parts[0] == "prompts" else {".py"})


def check_marker(folder: Path) -> list[str]:
    path = folder / "module.json"
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [
            f"service/{folder.name}/module.json：缺少有效的结构说明；"
            "用 uv run dev new-module 生成业务包"
        ]
    kind = content.get("kind") if isinstance(content, dict) else None
    if kind not in KINDS:
        kinds = "capability（能力包）或 workflow（流程包）"
        return [f"service/{folder.name}/module.json：kind 必须写 {kinds}"]
    if content != descriptor(folder.name, kind):
        return [f"service/{folder.name}/module.json：结构说明与标准业务包不一致"]
    return []
