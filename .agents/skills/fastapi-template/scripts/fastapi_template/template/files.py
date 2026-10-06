"""
框架更新的文件范围与模板来源。沿用 framework.lock 的范围，排除项目自己的登记与依赖。
路径逐项检查，不允许链接或越出项目目录的文件参加复制和更新。
"""

import hashlib
import json
import subprocess
import tomllib
from pathlib import Path
from typing import Any

from shared.modules.validation.framework_lock import LOCKED, REGISTRATION, SUFFIXES

SOURCE_FILE = "template-source.json"
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


# 仅列出框架自身文件；项目依赖、登记和迁移版本始终由项目维护。
def managed_files(project: Path) -> dict[str, bytes]:
    found = {}
    entries = (*LOCKED, "tools") if (project / "server/tools").exists() else LOCKED
    for entry in entries:
        if entry == "pyproject.toml":
            continue
        relative = entry.removeprefix("../") if entry.startswith("../") else f"server/{entry}"
        base = safe_path(project, relative)
        paths = [base] if base.is_file() else sorted(base.rglob("*"))
        for path in paths:
            name = path.relative_to(project).as_posix()
            if (
                path.suffix in SUFFIXES
                and "__pycache__" not in path.parts
                and name not in {f"server/{item}" for item in REGISTRATION}
            ):
                checked = safe_path(project, name)
                if checked.is_file():
                    found[name] = checked.read_bytes()
    return found


# 用实际文件摘要记录来源，版本名称只作说明，不代替文件比较。
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


# 来源摘要作为项目文件保存，便于今后找到对应的旧模板。
def save_provenance(target: Path, source: Path) -> None:
    path = safe_path(target, SOURCE_FILE)
    path.write_text(
        json.dumps(provenance(source), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


# 有来源记录的项目必须使用相同旧模板；旧项目可明确传入首次采用的模板目录。
def check_base(target: Path, base: Path) -> None:
    path = safe_path(target, SOURCE_FILE)
    if path.exists():
        recorded = json.loads(path.read_text(encoding="utf-8"))
        if recorded["files"] != provenance(base)["files"]:
            raise ValueError("旧模板与 template-source.json 不一致，请取出项目上次采用的模板版本")


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
