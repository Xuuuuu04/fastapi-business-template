import ast
import hashlib
import json
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shared.modules.validation import framework_files

SOURCE_FILE = "template-source.json"
LIST_MODULES = (
    ("server/shared/modules/validation/framework_files.py", "FRAMEWORK"),
    ("server/shared/modules/validation/framework_lock.py", "LOCKED"),
)
MANUAL_FILES = (
    "server/pyproject.toml",
    "server/uv.lock",
    "server/.env.example",
    "server/app/setup/catalog.py",
    "server/app/api/routers.py",
    "server/service",
    "server/app/api/v1",
    "server/migrations/versions",
    "AGENTS.md",
    "CLAUDE.md",
    "server/README.md",
    "server/service/README.md",
    "server/tests/README.md",
    "CHANGELOG.md",
    ".github",
)


def safe_path(root: Path, name: str) -> Path:
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"文件路径不安全：{name}")
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"文件路径越出项目：{name}")
    for part in [path, *path.parents]:
        if part == root:
            break
        if part.is_symlink():
            raise ValueError(f"不处理链接：{name}")
    return path


@dataclass(frozen=True)
class Manifest:
    framework: tuple[str, ...]
    registration: tuple[str, ...]
    suffixes: tuple[str, ...]


def manifest(template: Path) -> Manifest:
    found = [
        (module, first) for module, first in LIST_MODULES if safe_path(template, module).is_file()
    ]
    if not found:
        return Manifest(
            framework_files.FRAMEWORK, framework_files.REGISTRATION, framework_files.SUFFIXES
        )
    module, first = found[0]
    path = safe_path(template, module)
    names = (first, "REGISTRATION", "SUFFIXES")
    values = {
        target.id: ast.literal_eval(node.value)
        for node in ast.parse(path.read_text(encoding="utf-8")).body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id in names
    }
    missing = [name for name in names if name not in values]
    if missing:
        raise ValueError(f"{module} 缺少框架清单常量：{'、'.join(missing)}")
    return Manifest(*(tuple(values[name]) for name in names))


def managed_files(project: Path, listing: Manifest | None = None) -> dict[str, bytes]:
    listing = listing or manifest(project)
    found = {}
    framework = listing.framework
    entries = (*framework, "tools") if (project / "server/tools").exists() else framework
    for entry in entries:
        if entry == "pyproject.toml":
            continue
        relative = entry.removeprefix("../") if entry.startswith("../") else f"server/{entry}"
        base = safe_path(project, relative)
        paths = [base] if base.is_file() else sorted(base.rglob("*"))
        for path in paths:
            name = path.relative_to(project).as_posix()
            if (
                path.suffix in listing.suffixes
                and "__pycache__" not in path.parts
                and name not in {f"server/{item}" for item in listing.registration}
            ):
                checked = safe_path(project, name)
                if checked.is_file():
                    found[name] = checked.read_bytes()
    return found


def provenance(source: Path) -> dict[str, Any]:
    metadata = tomllib.loads((source / "server/pyproject.toml").read_text(encoding="utf-8"))
    revision = ""
    if (source / ".git").exists():
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=source, capture_output=True, text=True, check=True
        )
        revision = result.stdout.strip()
    return {
        "schema_version": 1,
        "version": metadata["project"]["version"],
        "revision": revision,
        "files": {
            name: hashlib.sha256(content).hexdigest()
            for name, content in managed_files(source).items()
        },
    }


def save_provenance(target: Path, source: Path) -> None:
    path = safe_path(target, SOURCE_FILE)
    path.write_text(
        json.dumps(provenance(source), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def check_base(target: Path, base: Path, listing: Manifest | None = None) -> list[str]:
    path = safe_path(target, SOURCE_FILE)
    if not path.exists():
        return []
    recorded = json.loads(path.read_text(encoding="utf-8"))
    different = [
        name for name, digest in recorded["files"].items() if file_digest(base, name) != digest
    ]
    if different:
        version = recorded.get("version", "未知")
        revision = recorded.get("revision") or "未记录"
        raise ValueError(
            f"旧模板与 template-source.json 不一致：{'、'.join(sorted(different)[:3])} "
            f"等 {len(different)} 个文件不同。请按记录的版本 {version}（提交 {revision}）"
            "取出旧模板，并在新模板的 server/ 下运行升级"
        )
    return sorted(managed_files(base, listing).keys() - recorded["files"].keys())


def file_digest(root: Path, name: str) -> str | None:
    path = safe_path(root, name)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def manual_changes(base: Path, source: Path) -> list[str]:
    changed = []
    for entry in MANUAL_FILES:
        before, after = safe_path(base, entry), safe_path(source, entry)
        files = {entry}
        for root, path in ((base, before), (source, after)):
            if path.is_dir():
                files |= {
                    item.relative_to(root).as_posix()
                    for item in path.rglob("*")
                    if item.is_file() and "__pycache__" not in item.parts
                }
        for name in sorted(files):
            old, new = safe_path(base, name), safe_path(source, name)
            old_value = old.read_bytes() if old.is_file() else None
            new_value = new.read_bytes() if new.is_file() else None
            if old_value != new_value:
                changed.append(name)
    return sorted(changed)
