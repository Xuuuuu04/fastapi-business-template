import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

from fastapi_template.template.files import (
    check_base,
    managed_files,
    manifest,
    manual_changes,
    safe_path,
    save_provenance,
)


@dataclass(frozen=True)
class Change:
    name: str
    state: str
    content: bytes | None


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


def update_plan(target: Path, base: Path, source: Path) -> tuple[list[Change], list[str]]:
    listing = manifest(source)
    fresh = set(check_base(target, base, listing))
    old = {
        name: content for name, content in managed_files(base, listing).items() if name not in fresh
    }
    new = managed_files(source, listing)
    changes = []
    for name in sorted(old.keys() | new.keys()):
        path = safe_path(target, name)
        local = path.read_bytes() if path.exists() else None
        change = compare_file(name, old.get(name), local, new.get(name))
        if change:
            changes.append(change)
    return changes, manual_changes(base, source)


def apply_plan(target: Path, base: Path, source: Path, expected: list[Change]) -> None:
    current, _ = update_plan(target, base, source)
    if current != expected:
        raise ValueError("文件在预览后发生变化，请重新预览")
    if any(change.state == "conflict" for change in current):
        raise ValueError("存在冲突，所有文件保持原样")
    for change in current:
        write_content(safe_path(target, change.name), change.content)
    save_provenance(target, source)


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
