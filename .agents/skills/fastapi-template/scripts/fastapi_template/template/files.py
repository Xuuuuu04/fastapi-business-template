import ast
import hashlib
import json
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SOURCE_FILE = "template-source.json"
FRAMEWORK_LIST = "server/shared/modules/validation/framework_files.py"
PROVENANCE_KEYS = ("schema_version", "version", "revision", "files")
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
    "CHANGELOG.md",
    ".github/workflows",
    ".github/pull_request_template.md",
)


def safe_path(root: Path, name: str) -> Path:
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"文件路径不安全：{name}")
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"文件路径指向项目目录之外：{name}")
    for part in [path, *path.parents]:
        if part == root:
            break
        if part.is_symlink():
            raise ValueError(f"不处理符号链接：{name}")
    return path


@dataclass(frozen=True)
class Manifest:
    framework: tuple[str, ...]
    registration: tuple[str, ...]
    suffixes: tuple[str, ...]


def manifest(template: Path) -> Manifest:
    path = safe_path(template, FRAMEWORK_LIST)
    if not path.is_file():
        raise ValueError(f"模板缺少框架清单 {FRAMEWORK_LIST}")
    names = ("FRAMEWORK", "REGISTRATION", "SUFFIXES")
    values = {
        target.id: ast.literal_eval(node.value)
        for node in ast.parse(path.read_text(encoding="utf-8")).body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id in names
    }
    missing = [name for name in names if name not in values]
    if missing:
        raise ValueError(f"{FRAMEWORK_LIST} 缺少框架清单常量：{'、'.join(missing)}")
    return Manifest(*(tuple(values[name]) for name in names))


def project_path(entry: str) -> str:
    return entry.removeprefix("../") if entry.startswith("../") else f"server/{entry}"


def managed_files(project: Path, listing: Manifest | None = None) -> dict[str, bytes]:
    listing = listing or manifest(project)
    found = {}
    for entry in listing.framework:
        if entry == "pyproject.toml":
            continue
        base = safe_path(project, project_path(entry))
        paths = [base] if base.is_file() else sorted(base.rglob("*"))
        for path in paths:
            name = path.relative_to(project).as_posix()
            if (
                path.suffix in listing.suffixes
                and "__pycache__" not in path.parts
                and not any(
                    name == product or name.startswith(product + "/")
                    for product in map(project_path, listing.registration)
                )
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
    if not path.is_file():
        raise ValueError(f"项目缺少 {SOURCE_FILE}，无法确定原模板版本，不能自动升级")
    recorded = json.loads(path.read_text(encoding="utf-8"))
    missing = [key for key in PROVENANCE_KEYS if key not in recorded]
    if missing:
        raise ValueError(f"{SOURCE_FILE} 缺少 {'、'.join(missing)}")
    different = [
        name for name, digest in recorded["files"].items() if file_digest(base, name) != digest
    ]
    if different:
        revision = f"（提交 {recorded['revision']}）" if recorded["revision"] else ""
        raise ValueError(
            f"旧模板与 template-source.json 不一致：{'、'.join(sorted(different)[:3])} "
            f"等 {len(different)} 个文件不同。请按记录的版本 {recorded['version']}{revision}"
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
