"""
三份文件比较的框架更新：旧模板、项目现有文件、新模板。
只更新没有冲突的完整方案；有冲突时全部保留原样，不把冲突标记写进业务项目。
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

from fastapi_template.template.files import (
    check_base,
    managed_files,
    manual_changes,
    safe_path,
    save_provenance,
)


# 一项更新的内容与状态；冲突项的内容为空，不可应用。
@dataclass(frozen=True)
class Change:
    name: str
    state: str
    content: bytes | None


# Git 只在临时目录合并文本，不接触项目文件；冲突返回明确状态。
def merge_text(name: str, old: bytes, local: bytes, new: bytes) -> Change:
    if any(b"\0" in content for content in (old, local, new)):
        return Change(name, "conflict", None)
    with TemporaryDirectory(prefix="template-merge-") as folder:
        paths = [Path(folder) / part for part in ("local", "base", "new")]
        for path, content in zip(paths, (local, old, new), strict=True):
            path.write_bytes(content)
        result = subprocess.run(
            ["git", "merge-file", "-p", *map(str, paths)], capture_output=True, check=False
        )
    if result.returncode < 0 or result.returncode > 127:
        raise RuntimeError(f"文本比较失败：{name}；{result.stderr.decode(errors='replace')}")
    return Change(
        name,
        "merged" if result.returncode == 0 else "conflict",
        result.stdout if result.returncode == 0 else None,
    )


# 处理增加、修改、删除和两边同时改动，已相同的内容不产生写入。
def compare_file(
    name: str, old: bytes | None, local: bytes | None, new: bytes | None
) -> Change | None:
    if new == old or local == new:
        return None
    if local == old:
        return Change(name, "delete" if new is None else "update", new)
    if old is None or local is None or new is None:
        return Change(name, "conflict", None)
    return merge_text(name, old, local, new)


# 先检查所有目标和来源，再计算完整方案；依赖与登记变化单独列出人工处理。
def update_plan(target: Path, base: Path, source: Path) -> tuple[list[Change], list[str]]:
    check_base(target, base)
    old, new = managed_files(base), managed_files(source)
    changes = []
    for name in sorted(old.keys() | new.keys()):
        path = safe_path(target, name)
        local = path.read_bytes() if path.exists() else None
        change = compare_file(name, old.get(name), local, new.get(name))
        if change:
            changes.append(change)
    return changes, manual_changes(base, source)


# 应用前重新读取文件，失败时恢复本次写入；来源更新必须与文件更新一起成功。
def apply_plan(target: Path, base: Path, source: Path, expected: list[Change]) -> None:
    current, _ = update_plan(target, base, source)
    if current != expected:
        raise ValueError("文件在预览后发生变化，请重新预览")
    if any(change.state == "conflict" for change in current):
        raise ValueError("存在冲突，所有文件保持原样")
    originals = {
        change.name: safe_path(target, change.name).read_bytes()
        if safe_path(target, change.name).exists()
        else None
        for change in current
    }
    provenance_path = safe_path(target, "template-source.json")
    originals["template-source.json"] = (
        provenance_path.read_bytes() if provenance_path.exists() else None
    )
    try:
        for change in current:
            write_content(safe_path(target, change.name), change.content)
        save_provenance(target, source)
    except (OSError, ValueError, RuntimeError):
        for name, content in originals.items():
            write_content(safe_path(target, name), content)
        raise


# 保存或删除框架文件；临时文件位于同目录，替换单个文件时不会留下半份内容。
def write_content(path: Path, content: bytes | None) -> None:
    if content is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    with NamedTemporaryFile(prefix=f".{path.name}.", dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
    try:
        temporary.write_bytes(content)
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
