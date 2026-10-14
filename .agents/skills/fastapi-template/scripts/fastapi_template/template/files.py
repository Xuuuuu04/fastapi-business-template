"""
框架更新的文件范围与模板来源。沿用 framework.lock 的范围，排除项目自己的登记与依赖。
路径逐项检查，不允许链接或越出项目目录的文件参加复制和更新。
"""

import ast
import hashlib
import json
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shared.modules.validation import framework_lock

SOURCE_FILE = "template-source.json"
LOCK_MODULE = "server/shared/modules/validation/framework_lock.py"
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
    "doc/README.md",
    "server/README.md",
    "server/service/README.md",
    "server/tests/README.md",
    "CHANGELOG.md",
    ".github",
)


# 文件路径必须留在指定项目内，链接即使指向项目内也不参与自动写入。
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


# 框架清单：哪些目录和文件归模板管理。
@dataclass(frozen=True)
class Manifest:
    locked: tuple[str, ...]
    registration: tuple[str, ...]
    suffixes: tuple[str, ...]


# 从模板目录自己的 framework_lock.py 读出清单，只解析常量、不执行代码；
# 升级时用新模板的清单，不用当前进程可能更旧的版本。测试用的最小目录没有这个文件，用工具自带的清单。
def manifest(template: Path) -> Manifest:
    path = safe_path(template, LOCK_MODULE)
    if not path.is_file():
        return Manifest(framework_lock.LOCKED, framework_lock.REGISTRATION, framework_lock.SUFFIXES)
    names = ("LOCKED", "REGISTRATION", "SUFFIXES")
    values = {
        target.id: ast.literal_eval(node.value)
        for node in ast.parse(path.read_text(encoding="utf-8")).body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id in names
    }
    missing = [name for name in names if name not in values]
    if missing:
        raise ValueError(f"{LOCK_MODULE} 缺少框架清单常量：{'、'.join(missing)}")
    return Manifest(*(tuple(values[name]) for name in names))


# 仅列出框架自身文件；项目依赖、登记和迁移版本始终由项目维护。
def managed_files(project: Path, listing: Manifest | None = None) -> dict[str, bytes]:
    listing = listing or manifest(project)
    found = {}
    locked = listing.locked
    entries = (*locked, "tools") if (project / "server/tools").exists() else locked
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


# 用实际文件摘要记录来源，按来源模板自己的清单计算；版本名称只作说明，不代替文件比较。
def provenance(source: Path) -> dict[str, Any]:
    metadata = tomllib.loads((source / "server/pyproject.toml").read_text(encoding="utf-8"))
    revision = ""
    if (source / ".git").exists():
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=source, capture_output=True, text=True, check=True
        )
        revision = result.stdout.strip()
    # 没有锁文件的来源记为空，产品检查会保守地运行全部模板工具测试。
    lock = source / "server/framework.lock"
    return {
        "schema_version": 1,
        "version": metadata["project"]["version"],
        "revision": revision,
        "framework_lock": hashlib.sha256(lock.read_bytes()).hexdigest() if lock.is_file() else "",
        "files": {
            name: hashlib.sha256(content).hexdigest()
            for name, content in managed_files(source).items()
        },
    }


# 来源摘要作为项目文件保存，便于今后找到对应的旧模板。
def save_provenance(target: Path, source: Path) -> None:
    path = safe_path(target, SOURCE_FILE)
    path.write_text(
        json.dumps(provenance(source), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


# 有来源记录的项目必须使用相同旧模板：记录里的每个文件都和旧模板一致。
# 返回新清单有、来源记录没有的文件，升级时按新增文件处理；旧项目可明确传入首次采用的模板目录。
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


# 旧模板里一个文件的摘要；文件不存在时为空。
def file_digest(root: Path, name: str) -> str | None:
    path = safe_path(root, name)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


# 项目所有文件也比较上游变化，但只列出人工处理位置，不自动保存。
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
